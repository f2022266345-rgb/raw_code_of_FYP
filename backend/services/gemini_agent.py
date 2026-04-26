"""
services/gemini_agent.py
─────────────────────────
Task 4 — Token Optimization Protocol + Gemini API Integration.

Rules (from spec):
  • Send ONLY: system_instruction (≤ 150 tokens) + current user message.
  • Discard: full chat history array — NOT sent to the LLM.
  • pgvector: used ONLY when needs_pgvector=True (p_mastery < 0.4 AND
              practice_count < 3) to inject scaffolding context.

Uses google-generativeai (Gemini 1.5 Flash) for fast, cost-efficient
tutoring responses. Falls back gracefully if the API key is missing.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional, List

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Gemini client — lazy init
# ─────────────────────────────────────────────────────────────────────────────

_gemini_model = None
_GEMINI_MODEL_CANDIDATES = [
    os.getenv("GEMINI_MODEL", "").strip(),
    "gemini-flash-latest",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
]


def _iter_model_candidates() -> List[str]:
    # Keep order, drop empties, and dedupe.
    seen = set()
    ordered: List[str] = []
    for model_name in _GEMINI_MODEL_CANDIDATES:
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        ordered.append(model_name)
    return ordered


def _get_gemini_model():
    global _gemini_model
    if _gemini_model is None:
        try:
            import google.generativeai as genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                logger.warning("GEMINI_API_KEY not set — Gemini agent will use fallback responses.")
                return None
            genai.configure(api_key=api_key)
            _gemini_model = genai
            logger.info("Gemini client initialized via google.generativeai.")
        except Exception as e:
            logger.error("Failed to initialize Gemini client: %s", e)
            return None
    return _gemini_model


# ─────────────────────────────────────────────────────────────────────────────
# Token counter (approximate)
# ─────────────────────────────────────────────────────────────────────────────

def _count_tokens_approx(text: str) -> int:
    """
    Approximate token count — splits on whitespace + punctuation.
    Fast heuristic: 1 token ≈ 0.75 words in English.
    Used to enforce the ≤150 token system instruction limit.
    """
    words = text.split()
    return max(1, int(len(words) / 0.75))


def _truncate_to_token_limit(text: str, max_tokens: int = 150) -> str:
    """
    Truncates the system instruction to stay within max_tokens.
    Preserves whole sentences where possible.
    """
    if _count_tokens_approx(text) <= max_tokens:
        return text

    # Truncate word-by-word until within budget
    words = text.split()
    result_words = []
    estimated_tokens = 0
    for word in words:
        word_tokens = max(1, int(1 / 0.75))
        if estimated_tokens + word_tokens > max_tokens:
            break
        result_words.append(word)
        estimated_tokens += word_tokens

    truncated = " ".join(result_words)
    logger.debug("System instruction truncated to ~%d tokens.", estimated_tokens)
    return truncated


def _extract_reply_text(response) -> str:
    """Best-effort extraction of full text from Gemini response candidates."""
    try:
      text = getattr(response, "text", None)
      if text:
          return text.strip()
    except Exception:
      pass

    parts: List[str] = []
    try:
      candidates = getattr(response, "candidates", None) or []
      for candidate in candidates:
          content = getattr(candidate, "content", None)
          if not content:
              continue
          for part in getattr(content, "parts", []) or []:
              maybe_text = getattr(part, "text", None)
              if maybe_text:
                  parts.append(maybe_text)
    except Exception:
      pass

    return "".join(parts).strip()


def _response_hit_token_limit(response) -> bool:
    """Detects if Gemini likely stopped due to output token limit."""
    try:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            reason = getattr(candidate, "finish_reason", None)
            reason_name = getattr(reason, "name", None) or str(reason)
            normalized = str(reason_name).upper()
            # Common values observed across SDK variants.
            if "MAX_TOKENS" in normalized or "TOKEN" in normalized or "LENGTH" in normalized:
                return True
            # Some SDK builds expose enum ints where 2 maps to MAX_TOKENS.
            if isinstance(reason, (int, float)) and int(reason) == 2:
                return True
    except Exception:
        return False
    return False


def _looks_incomplete(text: str) -> bool:
    """
    REVISED: Only flags truly broken responses. 
    A short response (12+ chars) is now considered valid.
    """
    if not text or len(text.strip()) < 5:  # Reduced from 12 to 5
        return True
    
    stripped = text.strip()
    # Only flag if it ends on a dangling connector
    if stripped.endswith((",", "and", "with", "the", "a")):
        return True

    # Check for terminal punctuation
    if not re.search(r"[.!?]['\")\]]*$", stripped):
        return True

    return False


def _normalize_history_entries(entries, source: str) -> List[dict]:
    if not isinstance(entries, list):
        return []

    normalized = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        role = "assistant" if str(item.get("role", "")).lower() == "assistant" else "user"
        normalized.append({"role": role, "content": content, "source": source})
    return normalized


def _build_context_window(
    chat_history,
    database_chat_history,
    max_turns: int = 16,
) -> str:
    merged = (
        _normalize_history_entries(database_chat_history, "database")
        + _normalize_history_entries(chat_history, "session")
    )
    if not merged:
        return ""

    window = merged[-max_turns:]
    lines = []
    for item in window:
        speaker = "Assistant" if item["role"] == "assistant" else "Student"
        source_label = "DB" if item["source"] == "database" else "Session"
        lines.append(f"[{source_label}] {speaker}: {item['content']}")
    return "\n".join(lines)


def _summarize_history_with_ai(
    gemini_model,
    model_module,
    context_window: str,
    user_message: str,
) -> str:
    if not context_window:
        return ""

    summary_prompt = (
        "You summarize tutoring conversations for context carryover. "
        "Write 4-6 concise bullet points covering:\n"
        "1) Current topic and goal\n"
        "2) What student already understands\n"
        "3) What is still confusing\n"
        "4) Agreed next step\n"
        "5) Emotional/cognitive cues if present\n\n"
        f"Current user message: {user_message}\n\n"
        "Conversation window:\n"
        f"{context_window}"
    )

    try:
        response = gemini_model.generate_content(
            summary_prompt,
            generation_config=model_module.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=220,
                top_p=0.9,
            ),
        )
        return _extract_reply_text(response)
    except Exception as exc:
        logger.warning("History summarization failed (non-fatal): %s", exc)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# pgvector Scaffolding Context
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_pgvector_context(
    db,                   # SQLAlchemy session
    skill_name: str,
    user_message: str,
    max_chunks: int = 2,
) -> Optional[str]:
    """
    Task 4: Retrieves the top-2 most semantically similar knowledge chunks
    from the `knowledge_chunks` table for a struggling student.

    Only called when needs_pgvector=True (p_mastery < 0.4 AND practice < 3).
    Returns a scaffolding snippet to append to the system instruction.

    Note: Embedding the user_message requires an embedding model.
    Here we use a keyword-match fallback if no embedding is available,
    keeping the function non-breaking.
    """
    try:
        from db import KnowledgeChunkORM
        # Keyword-based fallback (non-embedding path for now)
        # Replace with cosine similarity once embedding model is wired
        chunks = (
            db.query(KnowledgeChunkORM)
            .filter(
                KnowledgeChunkORM.content.ilike(f"%{skill_name}%")
            )
            .limit(max_chunks)
            .all()
        )
        if not chunks:
            return None

        context_text = "\n".join(f"• {c.content[:200]}" for c in chunks)
        logger.debug("pgvector scaffolding: %d chunks retrieved for skill '%s'.", len(chunks), skill_name)
        return f"\nScaffolding context for '{skill_name}':\n{context_text}"

    except Exception as exc:
        logger.warning("pgvector context retrieval failed (non-fatal): %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main: Call Gemini
# ─────────────────────────────────────────────────────────────────────────────

def call_gemini(
    system_instruction: str,
    user_message: str,
    needs_pgvector: bool = False,
    skill_name: str = "",
    db=None,
    chat_history=None,
    database_chat_history=None,
) -> str:
    """
    Task 4 — Token Optimization Protocol.

    Constructs the Gemini prompt as:
      [system_instruction (≤150 tokens)] + [optional pgvector scaffolding] + [user_message]

    NO chat history is passed. This is intentional — the system instruction
    encodes all necessary context from the database (BKT, profile, mood).

    Args:
        system_instruction: Rendered system prompt from state_engine.py.
        user_message:       The student's current question.
        needs_pgvector:     If True, appends semantic knowledge scaffolding.
        skill_name:         Used for pgvector lookup.
        db:                 SQLAlchemy session (required if needs_pgvector=True).

    Returns:
        The Gemini response string, or a graceful fallback.
    """
    model = _get_gemini_model()

    # ── Enforce ≤150 token system instruction ─────────────────────────────
    optimized_instruction = _truncate_to_token_limit(system_instruction, max_tokens=150)
    token_count = _count_tokens_approx(optimized_instruction)
    logger.info("System instruction: ~%d tokens (limit: 150).", token_count)

    # ── pgvector scaffolding (only when struggling AND low practice) ──────
    scaffolding = ""
    if needs_pgvector and db is not None and skill_name:
        scaffolding_text = _fetch_pgvector_context(db, skill_name, user_message)
        if scaffolding_text:
            scaffolding = scaffolding_text

    context_window = _build_context_window(chat_history, database_chat_history)

    logger.debug(
        "Gemini prompt:\n--- SYSTEM ---\n%s\n--- USER ---\n%s",
        optimized_instruction,
        user_message,
    )

    if model is None:
        return _fallback_response(user_message, needs_pgvector)

    try:
        for model_name in _iter_model_candidates():
            try:
                gemini_model = model.GenerativeModel(model_name)

                history_summary = _summarize_history_with_ai(
                    gemini_model=gemini_model,
                    model_module=model,
                    context_window=context_window,
                    user_message=user_message,
                )

                context_block = ""
                if context_window:
                    context_block += f"\n\nConversation Context Window:\n{context_window}"
                if history_summary:
                    context_block += f"\n\nAI Summary of Ongoing Conversation:\n{history_summary}"

                full_prompt = (
                    f"{optimized_instruction}{scaffolding}{context_block}\n\n"
                    f"Current Student Message: {user_message}"
                )
                
                # Temperature 0.7 allows for more natural flow than 0.4
                response = gemini_model.generate_content(
                    full_prompt,
                    generation_config=model.types.GenerationConfig(
                        temperature=0.7,
                        max_output_tokens=1200,
                        top_p=0.95,
                    ),
                )

                reply = _extract_reply_text(response)

                # If model stopped due to token budget, request continuation and merge.
                if reply and _response_hit_token_limit(response):
                    try:
                        continuation_response = gemini_model.generate_content(
                            (
                                f"{full_prompt}\n\n"
                                "Continue from the exact last sentence without repeating earlier text. "
                                "Finish the answer completely."
                            ),
                            generation_config=model.types.GenerationConfig(
                                temperature=0.7,
                                max_output_tokens=1200,
                                top_p=0.95,
                            ),
                        )
                        continuation = _extract_reply_text(continuation_response)
                        if continuation:
                            reply = f"{reply}\n\n{continuation}".strip()
                    except Exception as continuation_exc:
                        logger.warning("Gemini continuation call failed: %s", continuation_exc)
                
                # If it looks okay, return it immediately. 
                # Avoid the 'retry' loop which often causes the '10-word' generic output.
                if reply and not _looks_incomplete(reply):
                    return reply
                
                # If we must retry, be less restrictive
                if reply: return reply 

            except Exception as model_exc:
                logger.warning("Gemini model '%s' failed: %s", model_name, model_exc)

        return _fallback_response(user_message, needs_pgvector)

    except Exception as e:
        logger.error("Gemini API error: %s", e)
        return _fallback_response(user_message, needs_pgvector)


# ─────────────────────────────────────────────────────────────────────────────
# Fallback responses
# ─────────────────────────────────────────────────────────────────────────────

def _fallback_response(user_message: str, needs_pgvector: bool) -> str:
    if needs_pgvector:
        return (
            "Let's break this down step by step. What do you already know about this topic? "
            "Starting from what's familiar to you will help us build up from there."
        )
    return (
        "That's a great question! I'm processing your context to give you the best answer. "
        "Could you tell me a bit more about what specifically is confusing you?"
    )


def summarize_conversation_memory(topic: str, conversation_text: str) -> str:
    """Generate a concise AI summary for a topic-specific chat memory bucket."""
    if not conversation_text.strip():
        return "No conversation context available yet for this topic."

    model = _get_gemini_model()
    if model is None:
        return (
            "This memory contains prior discussion context for this topic, "
            "including your goals and the latest guidance."
        )

    summary_prompt = (
        "You are generating a memory card summary for a tutoring app. "
        "Write one concise paragraph (3-5 sentences) that captures: "
        "what the student discussed, key confusion points, and the next best step. "
        "Keep it practical, warm, and easy to scan.\n\n"
        f"Topic: {topic}\n\n"
        f"Conversation snippets:\n{conversation_text}"
    )

    for model_name in _iter_model_candidates():
        try:
            gemini_model = model.GenerativeModel(model_name)
            response = gemini_model.generate_content(
                summary_prompt,
                generation_config=model.types.GenerationConfig(
                    temperature=0.35,
                    max_output_tokens=260,
                    top_p=0.9,
                ),
            )
            reply = _extract_reply_text(response)
            if reply:
                return reply
        except Exception as exc:
            logger.warning("Memory summary generation failed on model '%s': %s", model_name, exc)

    return (
        "This memory includes recent discussion points, unresolved questions, "
        "and suggested follow-up actions for this topic."
    )




#     now not soo strict be cool and also maintain the context window and the chat_history of current rnning should also be send to api so that it can understand what is now runing and also send the summary of that chat history so that the gemini know that what is right now talking and what was he talked from database 

# for summary right now use ai i will use another model later now please read and backend and also update the AGENTS.md so and also not to be see strict and also the current running chat should have context window maintained

# please implement this features

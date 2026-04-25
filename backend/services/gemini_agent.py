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


def _looks_incomplete(text: str) -> bool:
    """Heuristic check for truncated/mid-sentence model output."""
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) < 12:
        return True

    if stripped.endswith((",", ";", ":", "-", "(", "[")):
        return True

    last_word_match = re.search(r"([A-Za-z]+)\W*$", stripped)
    last_word = (last_word_match.group(1).lower() if last_word_match else "")
    if last_word in {"and", "or", "but", "so", "because", "if", "then", "that", "which", "who"}:
        return True

    if not re.search(r"[.!?]['\")\]]*$", stripped):
        return True

    return False


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

    # ── Build final prompt (Task 4 format) ────────────────────────────────
    # Format: System Instruction \n [Scaffolding?] \n User: <message>
    full_prompt = f"{optimized_instruction}{scaffolding}\n\nStudent: {user_message}"

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
                # Initialize the model
                gemini_model = model.GenerativeModel(model_name)
                
                # Generate content with token limits
                response = gemini_model.generate_content(
                    full_prompt,
                    generation_config=model.types.GenerationConfig(
                        temperature=0.6,
                        max_output_tokens=512,
                        top_p=0.9,
                    ),
                )

                reply = _extract_reply_text(response)
                if reply and _looks_incomplete(reply):
                    logger.warning(
                        "Gemini output looked incomplete; retrying once for completion. model=%s reply=%r",
                        model_name,
                        reply,
                    )
                    retry_prompt = (
                        f"{full_prompt}\n\n"
                        "Important: Return a complete response in full sentences. "
                        "Do not stop mid-sentence."
                    )
                    retry_response = gemini_model.generate_content(
                        retry_prompt,
                        generation_config=model.types.GenerationConfig(
                            temperature=0.4,
                            max_output_tokens=640,
                            top_p=0.9,
                        ),
                    )
                    retry_reply = _extract_reply_text(retry_response)
                    if retry_reply:
                        reply = retry_reply

                if reply:
                    logger.info("Gemini response generated with model: %s", model_name)
                    return reply
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

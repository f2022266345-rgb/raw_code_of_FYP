"""backend/services/gemini_agent.py

This module uses Google Gemini models.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional, List

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Gemini client — lazy init
# ─────────────────────────────────────────────────────────────────────────────

_gemini_client = None

def _iter_model_candidates() -> List[str]:
    # Keep order, drop empties, and dedupe.
    candidates = [
        os.getenv("GEMINI_MODEL", "").strip(),
        # Sensible defaults
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]
    seen = set()
    ordered: List[str] = []
    for model_name in candidates:
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        ordered.append(model_name)
    return ordered


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning(
            "GEMINI_API_KEY not set — using fallback responses."
        )
        return None

    try:
        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
        logger.info("Gemini client initialized.")
        return _gemini_client
    except Exception as exc:
        logger.error("Failed to initialize Gemini client: %s", exc)
        return None

# ─────────────────────────────────────────────────────────────────────────────
# Token counter (approximate) & Embeddings
# ─────────────────────────────────────────────────────────────────────────────

def generate_embedding(text: str) -> list[float]:
    """Generates a 1536-dimensional embedding using an embedding model.
    Uses Gemini's embedding model and pads to 1536 dims to match DB schema.
    """
    if not text.strip():
        return [0.0] * 1536
    try:
        from google import genai
        
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            logger.warning("GEMINI_API_KEY not set. Using zero vector.")
            return [0.0] * 1536
            
        client = genai.Client(api_key=gemini_key)
        embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004")
            
        response = client.models.embed_content(
            model=embedding_model,
            contents=text
        )
        
        embedding = response.embeddings[0].values
        if not embedding:
            logger.warning("Empty embedding returned from Gemini. Using zero vector.")
            return [0.0] * 1536
            
        if len(embedding) < 1536:
            embedding.extend([0.0] * (1536 - len(embedding)))
        elif len(embedding) > 1536:
            embedding = embedding[:1536]
            
        return embedding
    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc)
        return [0.0] * 1536


def _count_tokens(text: str) -> int:
    """
    Counts tokens accurately using the official Gemini SDK method.
    Falls back to a fast heuristic if the client is unavailable.
    """
    client = _get_gemini_client()
    if not client:
        return max(1, int(len(text.split()) / 0.75))
    try:
        response = client.models.count_tokens(
            model=_iter_model_candidates()[0],
            contents=text
        )
        return response.total_tokens
    except Exception:
        return max(1, int(len(text.split()) / 0.75))


def _truncate_to_token_limit(text: str, max_tokens: int = 150) -> str:
    """
    Truncates the system instruction to stay within max_tokens using accurate token counting.
    Uses binary search for efficiency instead of word-by-word API calls.
    """
    if _count_tokens(text) <= max_tokens:
        return text

    words = text.split()
    left, right = 0, len(words)
    best_text = ""
    
    while left <= right:
        mid = (left + right) // 2
        candidate = " ".join(words[:mid])
        if _count_tokens(candidate) <= max_tokens:
            best_text = candidate
            left = mid + 1
        else:
            right = mid - 1

    logger.debug("System instruction truncated.")
    return best_text


def _extract_reply_text(response) -> str:
    try:
        return (response.text or "").strip()
    except Exception:
        return ""


def _response_hit_token_limit(response) -> bool:
    try:
        # Check finish_reason
        if getattr(response.candidates[0], 'finish_reason', None) == 'MAX_TOKENS':
            return True
        return False
    except Exception:
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
    if not re.search(r"[.!?]['\"\)]*$", stripped):
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
        role = "model" if str(item.get("role", "")).lower() in ("assistant", "model") else "user"
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
        speaker = "Assistant" if item["role"] == "model" else "Student"
        source_label = "DB" if item["source"] == "database" else "Session"
        lines.append(f"[{source_label}] {speaker}: {item['content']}")
    return "\n".join(lines)


def _summarize_history_with_ai(
    client,
    model_name: str,
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
        from google.genai import types
        response = client.models.generate_content(
            model=model_name,
            contents=summary_prompt,
            config=types.GenerateContentConfig(
                system_instruction="You summarize tutoring conversations for context carryover.",
                temperature=0.2,
                max_output_tokens=260,
                top_p=0.9,
            )
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
    """
    try:
        from db import KnowledgeChunkORM
        embedding = generate_embedding(user_message)
        chunks = (
            db.query(KnowledgeChunkORM)
            .order_by(KnowledgeChunkORM.embedding.cosine_distance(embedding))
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
    user_id: str | None = None,
) -> str:
    """
    Constructs the Gemini prompt as:
      [system_instruction (≤150 tokens)] + [optional pgvector scaffolding] + [user_message]
    """
    client = _get_gemini_client()

    optimized_instruction = _truncate_to_token_limit(system_instruction, max_tokens=150)
    token_count = _count_tokens(optimized_instruction)
    logger.info("System instruction: ~%d tokens (limit: 150).", token_count)

    scaffolding = ""
    if needs_pgvector and db is not None and skill_name:
        scaffolding_text = _fetch_pgvector_context(db, skill_name, user_message)
        if scaffolding_text:
            scaffolding = scaffolding_text

    context_window = _build_context_window(chat_history, database_chat_history)

    if client is None:
        return _fallback_response(user_message, needs_pgvector)

    from google.genai import types

    try:
        for model_name in _iter_model_candidates():
            try:
                history_summary = _summarize_history_with_ai(
                    client=client,
                    model_name=model_name,
                    context_window=context_window,
                    user_message=user_message,
                )

                context_block = ""
                if context_window:
                    context_block += f"\n\nConversation Context Window:\n{context_window}"
                if history_summary:
                    context_block += f"\n\nAI Summary of Ongoing Conversation:\n{history_summary}"

                system_content = f"{optimized_instruction}{scaffolding}{context_block}".strip()
                user_content = f"Current Student Message: {user_message}".strip()

                response = client.models.generate_content(
                    model=model_name,
                    contents=user_content,
                    config=types.GenerateContentConfig(
                        system_instruction=system_content,
                        temperature=0.7,
                        max_output_tokens=1200,
                        top_p=0.95,
                    )
                )

                reply = _extract_reply_text(response)

                if reply and _response_hit_token_limit(response):
                    try:
                        continuation = client.models.generate_content(
                            model=model_name,
                            contents=f"Previous part of response: {reply}\n\nContinue from the exact last sentence without repeating earlier text. Finish the answer completely.",
                            config=types.GenerateContentConfig(
                                system_instruction=system_content,
                                temperature=0.7,
                                max_output_tokens=1200,
                                top_p=0.95,
                            )
                        )
                        continuation_text = _extract_reply_text(continuation)
                        if continuation_text:
                            reply = f"{reply}\n\n{continuation_text}".strip()
                    except Exception as continuation_exc:
                        logger.warning("Continuation call failed: %s", continuation_exc)

                if reply and not _looks_incomplete(reply):
                    final_reply = reply
                    try:
                        conv_text = "\n\n".join(filter(None, [context_window, user_message, final_reply]))
                        updates = extract_profile_updates(conv_text)
                        if isinstance(updates, dict) and db is not None and user_id:
                            try:
                                update_student_parameters(db, user_id, updates)
                            except Exception as uerr:
                                logger.warning("update_student_parameters failed: %s", uerr)
                    except Exception:
                        logger.debug("Profile update extraction skipped or failed.")
                    return final_reply

                if reply:
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


def summarize_conversation_memory(topic: str, conversation_text: str) -> str:
    """Generate a concise AI summary for a topic-specific chat memory bucket."""
    if not conversation_text.strip():
        return "No conversation context available yet for this topic."

    client = _get_gemini_client()
    if client is None:
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

    from google.genai import types
    for model_name in _iter_model_candidates():
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=summary_prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are generating a memory card summary for a tutoring app.",
                    temperature=0.35,
                    max_output_tokens=280,
                    top_p=0.9,
                )
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


def synthesize_and_embed_student_profile(db, user_id: str, raw_profile_text: str) -> None:
    client = _get_gemini_client()
    if not client: return
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=_iter_model_candidates()[0],
            contents=f"Raw onboarding data:\n{raw_profile_text}",
            config=types.GenerateContentConfig(
                system_instruction="You are an expert tutor. Summarize the student's profile into a single coherent paragraph, focusing on learning style, background, and any struggles (like anxiety).",
            )
        )
        summary = _extract_reply_text(response)
        if not summary: return

        embedding = generate_embedding(summary)
        from db import StudentModelEmbeddingORM
        record = db.query(StudentModelEmbeddingORM).filter_by(user_id=user_id).first()
        if not record:
            record = StudentModelEmbeddingORM(user_id=user_id, summary_text=summary, embedding=embedding)
            db.add(record)
        else:
            record.summary_text = summary
            record.embedding = embedding
        db.commit()
    except Exception as exc:
        logger.error("Synthesis failed: %s", exc)
        db.rollback()


def summarize_and_embed_episodic_memory(db, user_id: str, conversation_text: str) -> None:
    client = _get_gemini_client()
    if not client: return
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=_iter_model_candidates()[0],
            contents=conversation_text,
            config=types.GenerateContentConfig(
                system_instruction="Summarize this tutoring session in one paragraph. Focus on what was taught, what analogies were used, and the student's level of understanding.",
            )
        )
        summary = _extract_reply_text(response)
        if not summary: return

        embedding = generate_embedding(summary)
        from db import EpisodicMemoryORM
        record = EpisodicMemoryORM(user_id=user_id, summary_text=summary, embedding=embedding)
        db.add(record)
        db.commit()
    except Exception as exc:
        logger.error("Episodic memory synthesis failed: %s", exc)
        db.rollback()


def extract_profile_updates(conversation_text: str) -> dict:
    """
    Extracts profile update signals from a conversation.
    """
    if not conversation_text.strip():
        return {
            "learning_barriers_score": None,
            "wellness_support_needed": None,
            "social_support_needed": None,
            "notes": "empty conversation",
        }

    client = _get_gemini_client()
    if client is None:
        return {
            "learning_barriers_score": None,
            "wellness_support_needed": None,
            "social_support_needed": None,
            "notes": "llm unavailable",
        }

    system_prompt = (
        "You extract structured learning-risk signals from tutoring chats. "
        "Return ONLY a JSON object with keys: "
        "learning_barriers_score (0.0-1.0), wellness_support_needed (true/false), "
        "social_support_needed (true/false), notes (short string)."
    )

    user_prompt = (
        "Conversation:\n"
        f"{conversation_text}\n\n"
        "Output JSON only."
    )

    from google.genai import types
    for model_name in _iter_model_candidates():
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                    max_output_tokens=220,
                    top_p=0.9,
                    response_mime_type="application/json",
                )
            )
            reply = _extract_reply_text(response)
            parsed = _safe_parse_json(reply)
            if parsed:
                return parsed
        except Exception as exc:
            logger.warning("Profile update extraction failed on model '%s': %s", model_name, exc)

    return {
        "learning_barriers_score": None,
        "wellness_support_needed": None,
        "social_support_needed": None,
        "notes": "no structured output",
    }


def update_student_parameters(db, user_id: str, updates: dict) -> dict:
    """
    Apply structured profile updates to the InitialProfileORM for a user.
    """
    try:
        from db import InitialProfileORM

        profile = db.query(InitialProfileORM).filter(InitialProfileORM.user_id == user_id).first()
        if not profile:
            return {"updated": False, "reason": "no_profile"}

        applied = {}
        score = updates.get("learning_barriers_score")
        if isinstance(score, (int, float)):
            profile.learning_barriers_score = max(0.0, min(float(score), 1.0))
            applied["learning_barriers_score"] = profile.learning_barriers_score

        wellness = updates.get("wellness_support_needed")
        if isinstance(wellness, bool):
            profile.wellness_support_needed = wellness
            applied["wellness_support_needed"] = wellness
            if wellness is True:
                profile.requires_human_override = True
                applied["requires_human_override"] = True

        social = updates.get("social_support_needed")
        if isinstance(social, bool):
            profile.social_support_needed = social
            applied["social_support_needed"] = social

        notes = updates.get("notes")
        if notes and isinstance(notes, str):
            existing = profile.cognitive_rules or {}
            existing["last_notes"] = notes[:512]
            profile.cognitive_rules = existing
            applied["notes"] = existing["last_notes"]

        db.commit()
        return {"updated": True, "applied": applied}
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("Failed to apply student parameter updates: %s", exc)
        return {"updated": False, "reason": "error", "error": str(exc)}


def _safe_parse_json(text: str) -> Optional[dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None

#     now not soo strict be cool and also maintain the context window and the chat_history of current rnning should also be send to api so that it can understand what is now runing and also send the summary of that chat history so that the gemini know that what is right now talking and what was he talked from database 

# for summary right now use ai i will use another model later now please read and backend and also update the AGENTS.md so and also not to be see strict and also the current running chat should have context window maintained

# please implement this features

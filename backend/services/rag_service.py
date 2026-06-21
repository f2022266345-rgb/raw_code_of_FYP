"""
RAG (Retrieval-Augmented Generation) Service for LUMINA agents.

Retrieves relevant context from pgvector tables:
- episodic_memory  : user-specific past conversation summaries (top-k cosine)
- knowledge_chunks : curated domain knowledge filtered by agent_type (top-k cosine)
- student_model_embeddings : full student profile vibe check

Also provides helpers to write new memories after each chat turn.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def retrieve_rag_context(
    db: Session,
    user_id: str,
    query_text: str,
    agent_type: str = "academic",
    top_k_episodic: int = 3,
    top_k_knowledge: int = 2,
) -> str:
    """
    Full RAG pipeline. Returns a formatted string block ready for injection
    into the LLM system prompt.

    Retrieves:
      1. Top-k same-agent episodic memories (primary context for this agent)
      2. Top-k cross-agent episodic memories (context from other agents)
      3. Top-k knowledge chunks (agent-filtered, cosine similarity)
    """
    if not query_text.strip():
        return ""

    try:
        from services.gemini_agent import generate_embedding
        query_embedding = generate_embedding(query_text)
    except Exception as exc:
        logger.warning("RAG: embedding generation failed: %s", exc)
        return ""

    sections: List[str] = []

    # ── Same-agent memories (primary) ─────────────────────────────────────────
    own_memories = _retrieve_episodic(
        db, user_id, query_embedding, top_k_episodic, agent_type=agent_type
    )
    if own_memories:
        formatted = "\n".join(f"  Memory {i+1}: {chunk}" for i, chunk in enumerate(own_memories))
        sections.append(f"Your Previous Conversations with This Agent:\n{formatted}")

    # ── Cross-agent memories (context from other agents, 1-2 entries) ─────────
    cross_memories = _retrieve_episodic(
        db, user_id, query_embedding, top_k=2, agent_type=None, exclude_agent=agent_type
    )
    if cross_memories:
        formatted = "\n".join(f"  Cross-agent note {i+1}: {chunk[:300]}" for i, chunk in enumerate(cross_memories))
        sections.append(f"Context from Other Agents (what they observed about you):\n{formatted}")

    # ── Domain knowledge ──────────────────────────────────────────────────────
    knowledge = _retrieve_knowledge(db, query_embedding, agent_type, top_k_knowledge)
    if knowledge:
        formatted = "\n".join(f"  Knowledge {i+1}: {chunk}" for i, chunk in enumerate(knowledge))
        sections.append(f"Relevant Domain Knowledge:\n{formatted}")

    return "\n\n".join(sections)


def embed_and_save_exchange(
    db: Session,
    user_id: str,
    agent_type: str,
    user_message: str,
    assistant_response: str,
) -> None:
    """
    Saves a chat exchange to episodic_memory with a pgvector embedding.
    Stores agent_type so each agent's memories can be retrieved separately
    while cross-agent context is still accessible when needed.
    """
    exchange_text = f"[{agent_type.upper()} Agent Conversation]\nStudent: {user_message}\nAgent: {assistant_response}"
    text_to_embed = exchange_text[:2000]

    try:
        from services.gemini_agent import generate_embedding
        from db import EpisodicMemoryORM

        embedding = generate_embedding(text_to_embed)
        record = EpisodicMemoryORM(
            user_id=user_id,
            agent_type=agent_type,          # scoped to this agent
            summary_text=text_to_embed,
            embedding=embedding,
        )
        db.add(record)
        db.commit()
        logger.info("Episodic memory saved | user=%s agent=%s", user_id, agent_type)
    except Exception as exc:
        logger.warning("embed_and_save_exchange failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


def write_cross_agent_memory(
    db: Session,
    user_id: str,
    source_agent: str,
    key_context: str,
    mood: Optional[str] = None,
    cognitive_state: Optional[str] = None,
) -> None:
    """
    Writes a structured state update to agent_memory so other agents can read
    what this agent observed. This implements cross-agent long-term memory.

    All agents (Academic, Social, Wellness) call this after responding;
    all agents read the latest entry during context retrieval.
    """
    try:
        from db import AgentMemoryORM
        memory = AgentMemoryORM(
            user_id=user_id,
            source_agent=source_agent,
            mood=mood,
            cognitive_state=cognitive_state,
            payload={"key_context": key_context[:600] if key_context else ""},
        )
        db.add(memory)
        db.commit()
        logger.debug("Cross-agent memory written | user=%s from=%s", user_id, source_agent)
    except Exception as exc:
        logger.warning("write_cross_agent_memory failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _retrieve_episodic(
    db: Session,
    user_id: str,
    embedding: list,
    top_k: int,
    agent_type: Optional[str] = None,
    exclude_agent: Optional[str] = None,
) -> List[str]:
    """
    Retrieves top-k episodic memories by cosine similarity.

    agent_type=None  → returns ALL memories regardless of agent (legacy / cross-agent)
    agent_type="academic" → returns only Academic Agent memories
    exclude_agent="academic" → returns memories NOT from Academic (cross-agent view)
    """
    try:
        from db import EpisodicMemoryORM
        query = db.query(EpisodicMemoryORM).filter(
            EpisodicMemoryORM.user_id == user_id
        )
        if agent_type is not None:
            query = query.filter(EpisodicMemoryORM.agent_type == agent_type)
        if exclude_agent is not None:
            query = query.filter(
                (EpisodicMemoryORM.agent_type != exclude_agent)
                | (EpisodicMemoryORM.agent_type.is_(None))
            )
        rows = (
            query
            .order_by(EpisodicMemoryORM.embedding.cosine_distance(embedding))
            .limit(top_k)
            .all()
        )
        return [r.summary_text[:500] for r in rows if r.summary_text]
    except Exception as exc:
        logger.warning("RAG episodic retrieval failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return []


def _retrieve_knowledge(db: Session, embedding: list, agent_type: str, top_k: int) -> List[str]:
    try:
        from db import KnowledgeChunkORM
        from sqlalchemy import or_
        query = db.query(KnowledgeChunkORM)
        if agent_type in ("academic", "wellness", "social", "coordinator"):
            query = query.filter(
                or_(
                    KnowledgeChunkORM.agent_type == agent_type,
                    KnowledgeChunkORM.agent_type.is_(None),
                )
            )
        rows = (
            query
            .order_by(KnowledgeChunkORM.embedding.cosine_distance(embedding))
            .limit(top_k)
            .all()
        )
        return [f"[{r.title}] {r.content[:400]}" for r in rows if r.content]
    except Exception as exc:
        logger.warning("RAG knowledge retrieval failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return []

"""
services/context_retriever.py
─────────────────────────────
Task 1 — The "Shared Brain" Context Retrieval.

Queries the PostgreSQL database (shared with Express/Sequelize) for all
signals needed to build a state-driven prompt:

  • BktSkillMasteryORM  →  p_mastery for the current skill
  • InitialProfileORM   →  bloom_level, language_barrier_risk, learning_preferences
  • InteractionLogORM   →  latest sentiment_label + mood (emotional state)
  • AgentMemoryORM      →  latest cross-agent memory (Wellness writes, Academic reads)

Returns a StudentContext dataclass — the single source of truth for the
state engine and prompt builder.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from db import (
    AgentMemoryORM,
    BktSkillMasteryORM,
    InitialProfileORM,
    InteractionLogORM,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# StudentContext dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StudentContext:
    """
    Complete context snapshot for a student at a given moment.
    Passed to the StateEngine to determine condition A or B and build
    the system prompt.
    """
    user_id: str
    skill_name: str

    # ── From BktSkillMastery ────────────────────────────────────────────────
    p_mastery: float = 0.3             # [0, 1] — current BKT mastery probability
    p_transit: float = 0.10            # used for scaffolding hints
    p_guess: float = 0.15
    practice_count: int = 0

    # ── From InitialProfile ─────────────────────────────────────────────────
    bloom_level: int = 1               # [1–6] Bloom's taxonomy level
    language_barrier_risk: float = 0.2 # [0, 1] — Urdu-medium risk score
    language_preference: str = "english-only"
    study_pace: str = "moderate"       # slow | moderate | fast
    learning_styles: dict = field(default_factory=dict)  # VARK scores

    # ── From InteractionLog (latest entry) ──────────────────────────────────
    sentiment_label: str = "neutral"   # positive | neutral | negative
    sentiment_score: float = 0.0       # [-1, 1]
    mood: str = "Focused"

    # ── From AgentMemory (cross-agent sync) ─────────────────────────────────
    wellness_mood: Optional[str] = None           # Latest mood from Wellness Agent
    wellness_sentiment: Optional[str] = None      # Latest sentiment from Wellness Agent
    cognitive_state: Optional[str] = None         # FLOW_STATE | CRITICAL_STRUGGLE etc.

    # ── Derived helpers ─────────────────────────────────────────────────────
    @property
    def effective_mood(self) -> str:
        """
        Returns the most recent mood: Wellness Agent's update takes priority
        over the raw InteractionLog entry (cross-agent sync applied).
        """
        return self.wellness_mood or self.mood

    @property
    def effective_sentiment(self) -> str:
        return self.wellness_sentiment or self.sentiment_label

    @property
    def needs_urdu_support(self) -> bool:
        return (
            self.language_barrier_risk > 0.6
            or self.language_preference in ("urdu-primary", "bilingual")
        )


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval function
# ─────────────────────────────────────────────────────────────────────────────

def get_student_context(
    db: Session,
    user_id: str,
    skill_name: str,
) -> StudentContext:
    """
    Performs 4 targeted database queries and assembles a StudentContext.

    Args:
        db:         SQLAlchemy session (injected via FastAPI Depends).
        user_id:    The UUID stored in bkt_skill_mastery.user_id etc.
        skill_name: The specific skill being studied right now.

    Returns:
        A fully populated StudentContext (with safe defaults on missing data).
    """
    ctx = StudentContext(user_id=user_id, skill_name=skill_name)

    # ── Query 1: BKT Skill Mastery ───────────────────────────────────────────
    try:
        bkt_row = (
            db.query(BktSkillMasteryORM)
            .filter(
                BktSkillMasteryORM.user_id == user_id,
                BktSkillMasteryORM.skill_name == skill_name,
            )
            .first()
        )
        if bkt_row:
            ctx.p_mastery = float(bkt_row.p_mastery or 0.3)
            ctx.p_transit = float(bkt_row.p_transit or 0.10)
            ctx.p_guess = float(bkt_row.p_guess or 0.15)
            ctx.practice_count = int(bkt_row.practice_count or 0)
            logger.debug("BKT [%s] p_mastery=%.3f", skill_name, ctx.p_mastery)
        else:
            logger.warning("No BKT row for user=%s skill=%s — using defaults.", user_id, skill_name)
    except Exception as exc:
        logger.error("BKT query failed: %s", exc)
        db.rollback()

    # ── Query 2: Initial Profile ─────────────────────────────────────────────
    try:
        profile = (
            db.query(InitialProfileORM)
            .filter(InitialProfileORM.user_id == user_id)
            .first()
        )
        if profile:
            ctx.bloom_level = int(profile.bloom_level or 1)
            ctx.language_barrier_risk = float(profile.language_barrier_risk or 0.2)

            prefs = profile.learning_preferences or {}
            ctx.language_preference = prefs.get("languagePreference", "english-only")
            ctx.study_pace = prefs.get("studyPace", "moderate")
            ctx.learning_styles = prefs.get("learningStyles", {})
            logger.debug("Profile bloom=%d lang_risk=%.2f", ctx.bloom_level, ctx.language_barrier_risk)
    except Exception as exc:
        logger.error("InitialProfile query failed: %s", exc)
        db.rollback()

    # ── Query 3: Latest Interaction Log (emotional state) ────────────────────
    try:
        latest_log = (
            db.query(InteractionLogORM)
            .filter(InteractionLogORM.user_id == user_id)
            .order_by(desc(InteractionLogORM.created_at))
            .first()
        )
        if latest_log:
            ctx.sentiment_label = latest_log.sentiment_label or "neutral"
            ctx.sentiment_score = float(latest_log.sentiment_score or 0.0)
            ctx.mood = latest_log.mood or "Focused"
            logger.debug("Latest log → sentiment=%s mood=%s", ctx.sentiment_label, ctx.mood)
    except Exception as exc:
        logger.error("InteractionLog query failed: %s", exc)
        db.rollback()

    # ── Query 4: Agent Memory (cross-agent sync — Wellness → Academic) ────────
    try:
        latest_memory = (
            db.query(AgentMemoryORM)
            .filter(AgentMemoryORM.user_id == user_id)
            .order_by(desc(AgentMemoryORM.created_at))
            .first()
        )
        if latest_memory:
            ctx.wellness_mood = latest_memory.mood
            ctx.wellness_sentiment = latest_memory.sentiment_label
            ctx.cognitive_state = latest_memory.cognitive_state
            logger.debug(
                "AgentMemory from '%s' → mood=%s cognitive_state=%s",
                latest_memory.source_agent,
                latest_memory.mood,
                latest_memory.cognitive_state,
            )
    except Exception as exc:
        logger.error("AgentMemory query failed: %s", exc)
        db.rollback()

    return ctx

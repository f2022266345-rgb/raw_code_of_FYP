"""
services/context_retriever.py
─────────────────────────────
Task 1 — The "Shared Brain" Context Retrieval.

Queries PostgreSQL for ALL signals needed to build a state-driven, personalised prompt:

  1. BktSkillMasteryORM      → p_mastery for the current skill
  2. InitialProfileORM       → bloom_level, language_barrier_risk, learning_preferences,
                               university, major, cognitive_rules
  3. InteractionLogORM       → latest sentiment_label + mood
  4. AgentMemoryORM          → latest cross-agent memory (Wellness/Academic/Social write here)
  5. StudentModelEmbeddingORM → long-term profile vibe (pgvector)
  6. EpisodicMemoryORM       → top-3 cosine-similar past conversations (RAG)
  7. CognitiveStateORM       → Digital Twin live cognitive state
  8. WellnessStateORM        → Digital Twin wellness (30d stress, burnout)
  9. DigitalTwinPredictionORM → Digital Twin ML predictions (at-risk, recommended agent)

Returns a StudentContext dataclass — single source of truth for the state engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from db import (
    AgentMemoryORM,
    BktSkillMasteryORM,
    CognitiveStateORM,
    DigitalTwinPredictionORM,
    InitialProfileORM,
    InteractionLogORM,
    WellnessStateORM,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# StudentContext dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StudentContext:
    """
    Complete context snapshot for a student at a given moment.
    Fed into the StateEngine to determine persona and build system prompts.
    """
    user_id: str
    skill_name: str

    # ── From BktSkillMastery ────────────────────────────────────────────────
    p_mastery: float = 0.3
    p_transit: float = 0.10
    p_guess: float = 0.15
    practice_count: int = 0

    # ── From InitialProfile ─────────────────────────────────────────────────
    bloom_level: int = 1
    language_barrier_risk: float = 0.2
    language_preference: str = "english-only"
    study_pace: str = "moderate"
    learning_styles: dict = field(default_factory=dict)
    university: str = ""
    major: str = ""
    cognitive_rules: dict = field(default_factory=dict)
    wellness_support_needed: bool = False
    social_support_needed: bool = False
    active_agents: list = field(default_factory=list)

    # ── From InteractionLog ─────────────────────────────────────────────────
    sentiment_label: str = "neutral"
    sentiment_score: float = 0.0
    mood: str = "Focused"

    # ── From AgentMemory (cross-agent) ──────────────────────────────────────
    wellness_mood: Optional[str] = None
    wellness_sentiment: Optional[str] = None
    cognitive_state: Optional[str] = None
    cross_agent_context: Optional[str] = None

    # ── From pgvector long-term memory ──────────────────────────────────────
    student_model_summary: Optional[str] = None
    episodic_memories: List[str] = field(default_factory=list)
    episodic_memory_summary: Optional[str] = None  # kept for backwards compat

    # ── From Digital Twin (cognitive_state table) ───────────────────────────
    twin_bloom_level: int = 1
    twin_cognitive_state: str = "developing"
    twin_frustration: float = 0.3
    twin_motivation: float = 0.7
    twin_engagement: str = "engaged"
    twin_learning_velocity: float = 0.0

    # ── From Digital Twin (wellness_state table) ────────────────────────────
    twin_stress_30d: float = 0.3
    twin_burnout_risk: float = 0.0
    twin_social_score: float = 0.5

    # ── From Digital Twin (digital_twin_predictions table) ──────────────────
    twin_at_risk: float = 0.3
    twin_recommended_agent: str = "coordinator"
    twin_intervention_urgency: str = "normal"
    twin_predicted_correctness: float = 0.5

    # ── Derived helpers ─────────────────────────────────────────────────────
    @property
    def effective_mood(self) -> str:
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

    @property
    def effective_bloom(self) -> int:
        """Use Digital Twin bloom if available (more up-to-date), else InitialProfile bloom."""
        return self.twin_bloom_level if self.twin_bloom_level > 1 else self.bloom_level


# ─────────────────────────────────────────────────────────────────────────────
# Main retrieval function
# ─────────────────────────────────────────────────────────────────────────────

def get_student_context(
    db: Session,
    user_id: str,
    skill_name: str,
    user_message: str = "",
    agent_type: str = "academic",
) -> StudentContext:
    """
    Performs 9 targeted database queries and assembles a StudentContext.
    All queries are individually exception-safe — a failure in one does not
    abort the others.
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
            ctx.p_mastery      = float(bkt_row.p_mastery or 0.3)
            ctx.p_transit      = float(bkt_row.p_transit or 0.10)
            ctx.p_guess        = float(bkt_row.p_guess or 0.15)
            ctx.practice_count = int(bkt_row.practice_count or 0)
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
            ctx.bloom_level          = int(profile.bloom_level or 1)
            ctx.language_barrier_risk = float(profile.language_barrier_risk or 0.2)
            ctx.wellness_support_needed = bool(profile.wellness_support_needed)
            ctx.social_support_needed   = bool(profile.social_support_needed)
            ctx.active_agents           = list(profile.active_agents or [])
            ctx.cognitive_rules         = dict(profile.cognitive_rules or {})

            prefs = profile.learning_preferences or {}
            ctx.language_preference = prefs.get("languagePreference", "english-only")
            ctx.study_pace          = prefs.get("studyPace", "moderate")
            ctx.learning_styles     = prefs.get("learningStyles", {})

            user_profile = profile.user_profile or {}
            ctx.university = user_profile.get("university", "")
            ctx.major      = user_profile.get("program", user_profile.get("major", ""))
    except Exception as exc:
        logger.error("InitialProfile query failed: %s", exc)
        db.rollback()

    # ── Query 3: Latest Interaction Log ──────────────────────────────────────
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
            ctx.mood            = latest_log.mood or "Focused"
    except Exception as exc:
        logger.error("InteractionLog query failed: %s", exc)
        db.rollback()

    # ── Query 4: Agent Memory (cross-agent sync) ──────────────────────────────
    try:
        latest_memory = (
            db.query(AgentMemoryORM)
            .filter(AgentMemoryORM.user_id == user_id)
            .order_by(desc(AgentMemoryORM.created_at))
            .first()
        )
        if latest_memory:
            ctx.wellness_mood      = latest_memory.mood
            ctx.wellness_sentiment = latest_memory.sentiment_label
            ctx.cognitive_state    = latest_memory.cognitive_state
            payload = latest_memory.payload or {}
            key_context = payload.get("key_context", "")
            if key_context:
                ctx.cross_agent_context = f"[{latest_memory.source_agent} Agent observed]: {key_context}"
    except Exception as exc:
        logger.error("AgentMemory query failed: %s", exc)
        db.rollback()

    # ── Query 5: Student Model Embedding (long-term profile vibe) ─────────────
    try:
        from db import StudentModelEmbeddingORM
        student_model = db.query(StudentModelEmbeddingORM).filter_by(user_id=user_id).first()
        if student_model:
            ctx.student_model_summary = student_model.summary_text
    except Exception as exc:
        logger.error("StudentModelEmbedding query failed: %s", exc)
        db.rollback()

    # ── Query 6: Episodic Memory — Top-3 Cosine Similarity ───────────────────
    # NOTE: We skip the embedding call here to avoid a duplicate Gemini API call.
    # retrieve_rag_context() in agent_router.py already embeds user_message and
    # fetches episodic memories — those results are injected via rag_context in
    # build_prompt_package(). Doing it twice burns quota and risks rate-limiting.
    # If you ever call get_student_context() without a downstream RAG step,
    # re-enable this block by passing precomputed_embedding as a parameter.
    _ = user_message  # kept in signature for API compatibility

    # ── Query 7: Digital Twin — Cognitive State ───────────────────────────────
    try:
        cs_row = (
            db.query(CognitiveStateORM)
            .filter(CognitiveStateORM.user_id == user_id)
            .first()
        )
        if cs_row:
            ctx.twin_bloom_level      = int(cs_row.current_bloom_level or 1)
            ctx.twin_cognitive_state  = cs_row.cognitive_state or "developing"
            ctx.twin_frustration      = float(cs_row.frustration_estimate or 0.3)
            ctx.twin_motivation       = float(cs_row.motivation_index or 0.7)
            ctx.twin_engagement       = cs_row.engagement_level or "engaged"
            ctx.twin_learning_velocity = float(cs_row.learning_velocity or 0.0)
    except Exception as exc:
        logger.error("CognitiveState (Digital Twin) query failed: %s", exc)
        db.rollback()

    # ── Query 8: Digital Twin — Wellness State ────────────────────────────────
    try:
        ws_row = (
            db.query(WellnessStateORM)
            .filter(WellnessStateORM.user_id == user_id)
            .first()
        )
        if ws_row:
            ctx.twin_stress_30d  = float(ws_row.stress_level_30d or 0.3)
            ctx.twin_burnout_risk = float(ws_row.burnout_risk or 0.0)
            ctx.twin_social_score = float(ws_row.social_integration_score or 0.5)
    except Exception as exc:
        logger.error("WellnessState (Digital Twin) query failed: %s", exc)
        db.rollback()

    # ── Query 9: Digital Twin — Predictions ───────────────────────────────────
    try:
        pred_row = (
            db.query(DigitalTwinPredictionORM)
            .filter(DigitalTwinPredictionORM.user_id == user_id)
            .first()
        )
        if pred_row:
            ctx.twin_at_risk              = float(pred_row.at_risk_probability or 0.3)
            ctx.twin_recommended_agent    = pred_row.recommended_agent_type or "coordinator"
            ctx.twin_intervention_urgency = pred_row.intervention_urgency or "normal"
            ctx.twin_predicted_correctness = float(pred_row.predicted_next_problem_correctness or 0.5)
    except Exception as exc:
        logger.error("DigitalTwinPredictions query failed: %s", exc)
        db.rollback()

    logger.info(
        "Context loaded | user=%s skill=%s p_mastery=%.2f bloom=%d twin_state=%s at_risk=%.2f",
        user_id, skill_name, ctx.p_mastery, ctx.effective_bloom,
        ctx.twin_cognitive_state, ctx.twin_at_risk,
    )
    return ctx

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, JSON,
    String, Text, UniqueConstraint, create_engine, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from pgvector.sqlalchemy import Vector


EMBEDDING_DIM = 1536


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql://") and "+" not in raw_url.split("://", 1)[0]:
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw_url


DATABASE_URL = _normalize_database_url(
    os.getenv("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/FYP_backup")
)


class Base(DeclarativeBase):
    pass


class SessionORM(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)

    is_authenticated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_crisis_modal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    major: Mapped[str | None] = mapped_column(String(120), nullable=True)
    university: Mapped[str | None] = mapped_column(String(180), nullable=True)
    stress_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_phase: Mapped[str | None] = mapped_column(String(80), nullable=True)
    academic_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    social_battery: Mapped[str | None] = mapped_column(String(24), nullable=True)
    current_mood: Mapped[str | None] = mapped_column(String(60), nullable=True)

    is_analyzing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    academic_status: Mapped[str] = mapped_column(String(24), default="idle", nullable=False)
    social_status: Mapped[str] = mapped_column(String(24), default="idle", nullable=False)
    wellness_status: Mapped[str] = mapped_column(String(24), default="idle", nullable=False)

    academic_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    social_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    wellness_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    notifications = relationship("NotificationORM", back_populates="session", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessageORM", back_populates="session", cascade="all, delete-orphan")


class NotificationORM(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    type: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    session = relationship("SessionORM", back_populates="notifications")


class ChatMessageORM(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    agent_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)

    session = relationship("SessionORM", back_populates="chat_messages")


class StudentModelEmbeddingORM(Base):
    __tablename__ = "student_model_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


class EpisodicMemoryORM(Base):
    __tablename__ = "episodic_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    agent_type: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


class KnowledgeChunkORM(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_type: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


# ============================================================================
# ORM Mirrors of Sequelize-managed tables
# (FastAPI reads these tables; Sequelize owns schema creation via alter:true)
# These classes are read-only from FastAPI's perspective — do NOT call
# Base.metadata.create_all() for these; Sequelize already handles that.
# ============================================================================

class BktSkillMasteryORM(Base):
    """
    Mirror of `bkt_skill_mastery` table (created by Sequelize BktSkillMastery model).
    FastAPI uses this for Task 1 context retrieval.
    """
    __tablename__ = "bkt_skill_mastery"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    skill_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    p_mastery: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    p_init: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_transit: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_guess: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_slip: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_forget: Mapped[float | None] = mapped_column(Float, nullable=True)
    practice_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column("createdAt", DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column("updatedAt", DateTime(timezone=True), nullable=True)


class InitialProfileORM(Base):
    """
    Mirror of `initial_profiles` table (created by Sequelize InitialProfile model).
    FastAPI reads bloomLevel, languageBarrierRisk, learningPreferences.
    """
    __tablename__ = "initial_profiles"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    persistent_learner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    bloom_level: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1)
    language_barrier_risk: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.2)
    # JSONB columns — SQLAlchemy reads these as Python dicts
    learning_preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    user_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_prediction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    active_agents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Additional columns mirrored from Sequelize model for state sync
    learning_barriers_score: Mapped[float | None] = mapped_column("learning_barriers_score", Float, nullable=True, default=0.0)
    wellness_support_needed: Mapped[bool | None] = mapped_column("wellness_support_needed", Boolean, nullable=True, default=False)
    social_support_needed: Mapped[bool | None] = mapped_column("social_support_needed", Boolean, nullable=True, default=False)
    cognitive_rules: Mapped[dict | None] = mapped_column("cognitive_rules", JSON, nullable=True)
    requires_human_override: Mapped[bool | None] = mapped_column("requires_human_override", Boolean, nullable=True, default=False)
    last_assessment_date: Mapped[datetime | None] = mapped_column("last_assessment_date", DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column("createdAt", DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column("updatedAt", DateTime(timezone=True), nullable=True)


class InteractionLogORM(Base):
    """
    Mirror of `interaction_logs` table (created by Sequelize InteractionLog model).
    FastAPI reads latest sentimentLabel + mood for emotional state detection.
    """
    __tablename__ = "interaction_logs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    page_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    mood: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hints_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_on_page_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column("createdAt", DateTime(timezone=True), nullable=True)


class AgentMemoryORM(Base):
    """
    NEW TABLE — `agent_memory`
    Cross-agent shared memory for real-time emotional state synchronization.

    The Wellness Agent WRITES here (mood, sentiment updates).
    The Academic Agent READS the latest entry for this user to adjust tone.

    This is the "Shared Brain" (Task 3 — Memory Synchronization).
    Created by FastAPI's init_db(); not managed by Sequelize.
    """
    __tablename__ = "agent_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # Which agent last wrote this entry
    source_agent: Mapped[str] = mapped_column(String(50), nullable=False)  # wellness | academic | coordinator
    # Emotional state fields (written by Wellness Agent)
    mood: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(50), nullable=True)  # positive | neutral | negative
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)   # [-1, 1]
    # Cognitive state from trend engine (written by Academic Agent)
    cognitive_state: Mapped[str | None] = mapped_column(String(100), nullable=True)  # FLOW_STATE | CRITICAL_STRUGGLE ...
    # Free-form JSON for agent-specific payload
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


class AcademicPlanORM(Base):
    __tablename__ = "academic_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    skill_gaps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tutoring_schedule: Mapped[list | None] = mapped_column(JSON, nullable=True)
    resources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    milestones: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


class SocialPlanORM(Base):
    __tablename__ = "social_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    peer_mentor_match: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    club_recommendations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    check_in_schedule: Mapped[list | None] = mapped_column(JSON, nullable=True)
    workshops: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


class WellnessPlanORM(Base):
    __tablename__ = "wellness_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), default="Standard")
    counseling_referral: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    crisis_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


class SynthesizedPlanORM(Base):
    __tablename__ = "synthesized_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    academic_plan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    social_plan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wellness_plan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_level: Mapped[str] = mapped_column(String(24), default="Standard")
    intervention_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


class DeliveryLogORM(Base):
    __tablename__ = "deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    channel: Mapped[str] = mapped_column(String(24), default="portal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


class ProgressSnapshotORM(Base):
    __tablename__ = "progress_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    grades: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attendance_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    engagement_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


class OutcomeReportORM(Base):
    __tablename__ = "outcome_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    semester: Mapped[str] = mapped_column(String(24), nullable=False)
    initial_risk_level: Mapped[str | None] = mapped_column(String(24), nullable=True)
    final_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    effectiveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendations_next_cycle: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


# ============================================================================
# DIGITAL TWIN ORM MODELS
# Created by FastAPI's init_db(); also set up via backend/migrations/002_digital_twin_tables.sql
# ============================================================================

class StudentProfileORM(Base):
    __tablename__ = "student_profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), unique=True, nullable=False, index=True)
    education_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    university: Mapped[str | None] = mapped_column(String(255), nullable=True)
    major: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entrance_exam_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    english_proficiency: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language_barrier_risk: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.5)
    cultural_background: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    socioeconomic_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_generation_student: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    learning_style: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preferred_challenge_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    study_location: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    academic_support_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    wellness_support_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    social_support_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc)


class CognitiveStateORM(Base):
    __tablename__ = "cognitive_state"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), unique=True, nullable=False, index=True)
    current_bloom_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    bkt_mastery_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cognitive_state: Mapped[str] = mapped_column(String(50), default="developing", nullable=False)
    state_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    engagement_level: Mapped[str] = mapped_column(String(50), default="engaged", nullable=False)
    frustration_estimate: Mapped[float] = mapped_column(Float, default=0.3)
    motivation_index: Mapped[float] = mapped_column(Float, default=0.7)
    cognitive_load_estimate: Mapped[float] = mapped_column(Float, default=0.4)
    learning_velocity: Mapped[float] = mapped_column(Float, default=0.0)
    avg_time_per_problem: Mapped[float | None] = mapped_column(Float, nullable=True)
    session_duration_preference: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc)


class LearningInteractionORM(Base):
    __tablename__ = "learning_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    interaction_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    problem_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skill_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_on_task_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hints_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    mood: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stress_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interaction_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    device_type: Mapped[str | None] = mapped_column(String(50), nullable=True)


class SkillMasteryORM(Base):
    __tablename__ = "skill_mastery"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_skill_mastery_user_skill"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    skill_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p_mastery: Mapped[float] = mapped_column(Float, default=0.2)
    p_init: Mapped[float] = mapped_column(Float, default=0.2)
    p_transit: Mapped[float] = mapped_column(Float, default=0.1)
    p_guess: Mapped[float] = mapped_column(Float, default=0.25)
    p_slip: Mapped[float] = mapped_column(Float, default=0.05)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0)
    practice_count: Mapped[int] = mapped_column(Integer, default=0)
    last_practiced: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    days_since_practice: Mapped[int | None] = mapped_column(Integer, nullable=True)


class WellnessStateORM(Base):
    __tablename__ = "wellness_state"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), unique=True, nullable=False, index=True)
    stress_level_30d: Mapped[float] = mapped_column(Float, default=0.3)
    anxiety_markers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    burnout_risk: Mapped[float] = mapped_column(Float, default=0.0)
    has_study_group: Mapped[bool] = mapped_column(Boolean, default=False)
    peer_interaction_frequency: Mapped[str | None] = mapped_column(String(50), nullable=True)
    social_integration_score: Mapped[float] = mapped_column(Float, default=0.5)
    family_pressure_level: Mapped[int] = mapped_column(Integer, default=2)
    home_study_environment_quality: Mapped[str] = mapped_column(String(50), default="moderate")
    last_wellness_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recommended_intervention: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intervention_status: Mapped[str] = mapped_column(String(50), default="pending")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc)


class DigitalTwinPredictionORM(Base):
    __tablename__ = "digital_twin_predictions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), unique=True, nullable=False, index=True)
    predicted_next_problem_correctness: Mapped[float] = mapped_column(Float, default=0.5)
    predicted_learning_trajectory: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    at_risk_probability: Mapped[float] = mapped_column(Float, default=0.3)
    intervention_urgency: Mapped[str] = mapped_column(String(50), default="normal")
    recommended_agent_type: Mapped[str] = mapped_column(String(50), default="coordinator")
    recommended_pacing: Mapped[str | None] = mapped_column(String(50), nullable=True)
    recommended_learning_style_adjustment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prediction_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    model_version: Mapped[str] = mapped_column(String(50), default="baseline")


class LearningProgressORM(Base):
    __tablename__ = "learning_progress"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    current_topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    topic_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    problems_completed: Mapped[int] = mapped_column(Integer, default=0)
    problems_correct: Mapped[int] = mapped_column(Integer, default=0)
    estimated_completion_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    milestones_achieved: Mapped[list | None] = mapped_column(JSON, nullable=True)
    next_milestone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pacing_adjustments: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    language_support_level: Mapped[str] = mapped_column(String(50), default="none")
    chunking_size: Mapped[str] = mapped_column(String(50), default="medium")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc)


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


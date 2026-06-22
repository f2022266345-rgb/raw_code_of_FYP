"""
services/student_bootstrap.py
─────────────────────────────
Idempotent "ensure the student exists everywhere" helpers.

Called whenever a student logs in or talks to an agent, so that EVERY active
user has:
  1. A Digital Twin (student_profiles + cognitive_state + wellness_state +
     digital_twin_predictions rows) — otherwise GET /digital-twin/student/{id}
     404s and there is no live state to personalize from.
  2. A vector-DB record in `student_model_embeddings` (pgvector) — the long-term
     "profile vibe" the RAG layer reads to personalize agent replies.

All inserts use ON CONFLICT DO NOTHING and explicit timestamps, so this is safe
to call on every request. The vector embedding uses Gemini's EMBEDDING quota
(separate from the generate_content quota), so it does not eat the chat budget.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Digital Twin rows
# ─────────────────────────────────────────────────────────────────────────────

def ensure_digital_twin(db: Session, user_id: str) -> bool:
    """
    Create the four Digital Twin rows for this user if they don't exist yet.
    Pulls seed values from the student's InitialProfile when available.
    Returns True if anything was created.
    """
    try:
        exists = db.execute(
            text("SELECT 1 FROM cognitive_state WHERE user_id = :uid LIMIT 1"),
            {"uid": user_id},
        ).first()
        if exists:
            return False

        # Seed from InitialProfile if present.
        lbr = 0.3
        acad = well = soc = False
        try:
            from db import InitialProfileORM
            prof = db.query(InitialProfileORM).filter(InitialProfileORM.user_id == user_id).first()
            if prof:
                lbr = float(prof.language_barrier_risk or 0.3)
                acad = bool(getattr(prof, "academic_support_needed", False) or True)
                well = bool(prof.wellness_support_needed or False)
                soc = bool(prof.social_support_needed or False)
        except Exception as exc:
            logger.debug("ensure_digital_twin: profile seed skipped: %s", exc)

        db.execute(
            text("""
                INSERT INTO student_profiles
                    (user_id, education_level, first_language, english_proficiency,
                     language_barrier_risk, academic_support_needed,
                     wellness_support_needed, social_support_needed,
                     created_at, updated_at)
                VALUES (:uid, '1st_semester', 'urdu',
                    CASE WHEN :lbr > 0.5 THEN 'intermediate' ELSE 'advanced' END,
                    :lbr, :acad, :well, :soc, NOW(), NOW())
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"uid": user_id, "lbr": lbr, "acad": acad, "well": well, "soc": soc},
        )
        db.execute(
            text("""
                INSERT INTO cognitive_state
                    (user_id, current_bloom_level, cognitive_state, engagement_level,
                     frustration_estimate, motivation_index, cognitive_load_estimate,
                     learning_velocity, last_updated)
                VALUES (:uid, 1, 'developing', 'engaged', 0.3, 0.7, 0.4, 0.0, NOW())
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"uid": user_id},
        )
        db.execute(
            text("""
                INSERT INTO wellness_state (user_id, stress_level_30d, burnout_risk, social_integration_score, updated_at)
                VALUES (:uid, 0.3, 0.0, 0.5, NOW())
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"uid": user_id},
        )
        db.execute(
            text("""
                INSERT INTO digital_twin_predictions
                    (user_id, predicted_next_problem_correctness, at_risk_probability,
                     recommended_agent_type, confidence_score, model_version,
                     prediction_timestamp)
                VALUES (:uid, 0.5, 0.3, 'coordinator', 0.5, 'login_baseline', NOW())
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"uid": user_id},
        )
        db.commit()
        logger.info("Digital Twin baseline created on demand for %s", user_id)
        return True
    except Exception as exc:
        db.rollback()
        logger.warning("ensure_digital_twin failed for %s: %s", user_id, exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Vector-DB record (pgvector)
# ─────────────────────────────────────────────────────────────────────────────

def _build_profile_text(db: Session, user_id: str) -> str:
    """Compose a compact, structured profile string to embed (no LLM call)."""
    parts = [f"Student {user_id}."]
    try:
        from db import InitialProfileORM
        prof = db.query(InitialProfileORM).filter(InitialProfileORM.user_id == user_id).first()
        if prof:
            up = prof.user_profile or {}
            if isinstance(up, dict):
                for label, key in (
                    ("Name", "name"), ("Major", "major"), ("University", "university"),
                    ("Current phase", "currentPhase"), ("Mood", "currentMood"),
                    ("Social battery", "socialBattery"), ("Language", "languagePreference"),
                ):
                    val = up.get(key)
                    if val:
                        parts.append(f"{label}: {val}.")
                for label, key in (("Stress level", "stressLevel"), ("Academic confidence", "academicConfidence")):
                    val = up.get(key)
                    if val is not None:
                        parts.append(f"{label}: {val}.")
            if prof.bloom_level is not None:
                parts.append(f"Bloom level: {prof.bloom_level}.")
            if prof.language_barrier_risk is not None:
                parts.append(f"Language barrier risk: {round(float(prof.language_barrier_risk), 2)}.")
            prefs = prof.learning_preferences or {}
            if isinstance(prefs, dict) and prefs.get("studyPace"):
                parts.append(f"Study pace: {prefs['studyPace']}.")
            if prof.wellness_support_needed:
                parts.append("Needs wellness support.")
            if prof.social_support_needed:
                parts.append("Needs social support.")
    except Exception as exc:
        logger.debug("_build_profile_text: %s", exc)
    return " ".join(parts)


def ensure_student_vector(db: Session, user_id: str, force: bool = False) -> bool:
    """
    Make sure the student has a `student_model_embeddings` row (pgvector).
    Embeds a structured profile string using the embedding model (embedding
    quota, NOT generate quota). Returns True if a record was written.
    """
    try:
        from db import StudentModelEmbeddingORM
        existing = db.query(StudentModelEmbeddingORM).filter_by(user_id=user_id).first()
        if existing and not force:
            return False

        from services.gemini_agent import generate_embedding
        profile_text = _build_profile_text(db, user_id)
        embedding = generate_embedding(profile_text)

        if existing:
            existing.summary_text = profile_text
            existing.embedding = embedding
        else:
            db.add(StudentModelEmbeddingORM(
                user_id=user_id, summary_text=profile_text, embedding=embedding,
            ))
        db.commit()
        logger.info("Student vector record %s for %s", "refreshed" if existing else "created", user_id)
        return True
    except Exception as exc:
        db.rollback()
        logger.warning("ensure_student_vector failed for %s: %s", user_id, exc)
        return False


def ensure_student_personalization(db: Session, user_id: str) -> dict:
    """Ensure both the Digital Twin and the vector-DB record exist. Idempotent."""
    twin = ensure_digital_twin(db, user_id)
    vector = ensure_student_vector(db, user_id)
    return {"twin_created": twin, "vector_created": vector}

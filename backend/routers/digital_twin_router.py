"""
Digital Twin API Endpoints
Prefix: /api/digital-twin
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/digital-twin", tags=["digital-twin"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class InteractionData(BaseModel):
    problem_id: int
    skill_id: int
    correct: bool
    time_on_task_ms: int
    hints_used: int = 0
    attempt_count: int = 1
    cognitive_weight: float = 1.5
    mood: Optional[str] = None
    confidence_before: float = 0.5
    confidence_after: float = 0.5


class TwinUpdateRequest(BaseModel):
    user_id: str
    interaction: InteractionData


class InitializeTwinRequest(BaseModel):
    user_id: str
    initial_predictions: dict
    bloom_level: int = 1
    language_barrier_risk: float = 0.5


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
async def digital_twin_health():
    return {"status": "ok", "service": "digital-twin"}


@router.post("/initialize")
async def initialize_student_digital_twin(
    request: InitializeTwinRequest,
    db: Session = Depends(get_db),
):
    """Initialize Digital Twin for new student (called during onboarding)."""
    uid = request.user_id
    preds = request.initial_predictions

    try:
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
            {
                "uid": uid,
                "lbr": preds.get("language_barrier_risk", 0.5),
                "acad": bool(preds.get("academic_support_needed", False)),
                "well": bool(preds.get("wellness_support_needed", False)),
                "soc": bool(preds.get("social_support_needed", False)),
            },
        )

        db.execute(
            text("""
                INSERT INTO cognitive_state
                    (user_id, current_bloom_level, cognitive_state, engagement_level,
                     frustration_estimate, motivation_index, cognitive_load_estimate,
                     learning_velocity, last_updated)
                VALUES (:uid, 1, 'developing', 'engaged', 0.3, 0.8, 0.4, 0.0, NOW())
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"uid": uid},
        )

        db.execute(
            text("""
                INSERT INTO wellness_state (user_id, stress_level_30d, burnout_risk, social_integration_score, updated_at)
                VALUES (:uid, 0.4, 0.0, 0.5, NOW())
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"uid": uid},
        )

        recommended = "academic" if preds.get("academic_support_needed") else "coordinator"
        db.execute(
            text("""
                INSERT INTO digital_twin_predictions
                    (user_id, predicted_next_problem_correctness, at_risk_probability,
                     recommended_agent_type, confidence_score, model_version,
                     prediction_timestamp)
                VALUES (:uid, 0.5, 0.2, :agent, 0.6, 'onboarding_baseline', NOW())
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"uid": uid, "agent": recommended},
        )

        db.commit()

        return {
            "success": True,
            "message": f"Digital Twin initialized for {uid}",
            "initial_state": {
                "bloom_level": 1,
                "cognitive_state": "developing",
                "engagement": 0.8,
            },
        }
    except Exception as exc:
        db.rollback()
        logger.error("Twin init error for %s: %s", uid, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/student/{user_id}")
async def get_digital_twin(user_id: str, db: Session = Depends(get_db)):
    """Return the complete digital twin for a student."""
    try:
        cs = db.execute(
            text("""
                SELECT user_id, current_bloom_level, cognitive_state,
                       engagement_level, frustration_estimate, motivation_index
                FROM cognitive_state WHERE user_id = :uid
            """),
            {"uid": user_id},
        ).fetchone()

        if not cs:
            # Auto-create a baseline twin + vector record on first access (e.g.
            # at login) instead of 404-ing, so every student is personalized.
            try:
                from services.student_bootstrap import ensure_student_personalization
                ensure_student_personalization(db, user_id)
            except Exception as boot_exc:
                logger.debug("twin auto-create skipped: %s", boot_exc)
            cs = db.execute(
                text("""
                    SELECT user_id, current_bloom_level, cognitive_state,
                           engagement_level, frustration_estimate, motivation_index
                    FROM cognitive_state WHERE user_id = :uid
                """),
                {"uid": user_id},
            ).fetchone()

        if not cs:
            raise HTTPException(status_code=404, detail="No digital twin found for this user")

        cognitive_state = dict(cs._mapping)

        skills = db.execute(
            text("""
                SELECT skill_id, p_mastery, practice_count
                FROM skill_mastery WHERE user_id = :uid
                ORDER BY p_mastery DESC LIMIT 10
            """),
            {"uid": user_id},
        ).fetchall()

        preds = db.execute(
            text("""
                SELECT predicted_next_problem_correctness, at_risk_probability,
                       recommended_agent_type, confidence_score
                FROM digital_twin_predictions WHERE user_id = :uid
            """),
            {"uid": user_id},
        ).fetchone()

        wellness = db.execute(
            text("""
                SELECT stress_level_30d, burnout_risk, social_integration_score
                FROM wellness_state WHERE user_id = :uid
            """),
            {"uid": user_id},
        ).fetchone()

        return {
            "user_id": user_id,
            "cognitive_state": cognitive_state,
            "skill_mastery": [dict(s._mapping) for s in skills],
            "predictions": dict(preds._mapping) if preds else {},
            "wellness": dict(wellness._mapping) if wellness else {},
            "retrieved_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_digital_twin error for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/update")
async def update_digital_twin(
    request: TwinUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update digital twin with a new student interaction."""
    uid = request.user_id
    interaction = request.interaction

    try:
        db.execute(
            text("""
                INSERT INTO learning_interactions
                    (user_id, problem_id, skill_id, correct, time_on_task_ms,
                     hints_used, attempt_count, mood, interaction_timestamp)
                VALUES (:uid, :pid, :sid, :corr, :ttms, :hints, :att, :mood, NOW())
            """),
            {
                "uid": uid,
                "pid": interaction.problem_id,
                "sid": interaction.skill_id,
                "corr": interaction.correct,
                "ttms": interaction.time_on_task_ms,
                "hints": interaction.hints_used,
                "att": interaction.attempt_count,
                "mood": interaction.mood,
            },
        )

        current_mastery = db.execute(
            text("SELECT p_mastery FROM skill_mastery WHERE user_id = :uid AND skill_id = :sid"),
            {"uid": uid, "sid": interaction.skill_id},
        ).scalar()

        base = current_mastery or 0.2
        new_p_mastery = min(base + 0.1, 0.95) if interaction.correct else max(base - 0.05, 0.05)

        db.execute(
            text("""
                INSERT INTO skill_mastery (user_id, skill_id, p_mastery, practice_count, last_practiced)
                VALUES (:uid, :sid, :pm, 1, NOW())
                ON CONFLICT (user_id, skill_id) DO UPDATE SET
                    p_mastery      = :pm,
                    practice_count = skill_mastery.practice_count + 1,
                    correct_count  = skill_mastery.correct_count  + :inc_cc,
                    incorrect_count= skill_mastery.incorrect_count + :inc_ic,
                    last_practiced = NOW()
            """),
            {
                "uid": uid,
                "sid": interaction.skill_id,
                "pm": new_p_mastery,
                "inc_cc": 1 if interaction.correct else 0,
                "inc_ic": 0 if interaction.correct else 1,
            },
        )

        db.commit()

        return {
            "success": True,
            "message": "Digital Twin updated",
            "new_mastery": round(new_p_mastery, 4),
        }

    except Exception as exc:
        db.rollback()
        logger.error("update_digital_twin error for %s: %s", uid, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/analytics/{user_id}")
async def get_analytics(user_id: str, period: str = "7d", db: Session = Depends(get_db)):
    """Return learning analytics trend for the given period."""
    interval_map = {"7d": "7 days", "30d": "30 days", "90d": "90 days"}
    interval = interval_map.get(period, "7 days")

    try:
        trend = db.execute(
            text(f"""
                SELECT
                    DATE(interaction_timestamp) AS date,
                    COUNT(*) AS count,
                    ROUND(AVG(CASE WHEN correct THEN 1.0 ELSE 0.0 END)::numeric, 3) AS accuracy
                FROM learning_interactions
                WHERE user_id = :uid
                  AND interaction_timestamp > NOW() - INTERVAL '{interval}'
                GROUP BY DATE(interaction_timestamp)
                ORDER BY date
            """),
            {"uid": user_id},
        ).fetchall()

        skill_top = db.execute(
            text("""
                SELECT skill_id, p_mastery, practice_count
                FROM skill_mastery WHERE user_id = :uid
                ORDER BY p_mastery DESC LIMIT 5
            """),
            {"uid": user_id},
        ).fetchall()

        return {
            "user_id": user_id,
            "period": period,
            "trend": [dict(r._mapping) for r in trend],
            "top_skills": [dict(s._mapping) for s in skill_top],
        }

    except Exception as exc:
        logger.error("get_analytics error for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

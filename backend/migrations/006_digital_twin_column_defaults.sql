-- ============================================================
-- Migration 006: DB-level defaults for ALL Digital Twin columns
-- ============================================================
-- Root cause (recurring): the Digital Twin tables were created by
-- SQLAlchemy with PYTHON-side defaults only (default=...). Those
-- never reach PostgreSQL, so every NOT NULL column without an
-- explicit value in a raw INSERT throws NotNullViolation
-- (created_at, then state_confidence, then the next one...).
--
-- This migration sets database-level DEFAULTs on every Digital
-- Twin column to match the ORM defaults in db.py, once and for
-- all, so raw INSERTs in the routers/services can never fail on a
-- missing non-null column again.
--
-- Idempotent. Builds on 004 (timestamps) and 005 (skill BKT priors).
-- ============================================================

BEGIN;

-- ── cognitive_state ───────────────────────────────────────────────
ALTER TABLE cognitive_state ALTER COLUMN current_bloom_level     SET DEFAULT 1;
ALTER TABLE cognitive_state ALTER COLUMN cognitive_state         SET DEFAULT 'developing';
ALTER TABLE cognitive_state ALTER COLUMN state_confidence        SET DEFAULT 0.5;
ALTER TABLE cognitive_state ALTER COLUMN engagement_level        SET DEFAULT 'engaged';
ALTER TABLE cognitive_state ALTER COLUMN frustration_estimate    SET DEFAULT 0.3;
ALTER TABLE cognitive_state ALTER COLUMN motivation_index        SET DEFAULT 0.7;
ALTER TABLE cognitive_state ALTER COLUMN cognitive_load_estimate SET DEFAULT 0.4;
ALTER TABLE cognitive_state ALTER COLUMN learning_velocity       SET DEFAULT 0.0;

-- ── student_profiles ──────────────────────────────────────────────
ALTER TABLE student_profiles ALTER COLUMN language_barrier_risk   SET DEFAULT 0.5;
ALTER TABLE student_profiles ALTER COLUMN academic_support_needed SET DEFAULT FALSE;
ALTER TABLE student_profiles ALTER COLUMN wellness_support_needed SET DEFAULT FALSE;
ALTER TABLE student_profiles ALTER COLUMN social_support_needed   SET DEFAULT FALSE;

-- ── skill_mastery (counts; priors handled in 005) ─────────────────
ALTER TABLE skill_mastery ALTER COLUMN correct_count   SET DEFAULT 0;
ALTER TABLE skill_mastery ALTER COLUMN incorrect_count SET DEFAULT 0;
ALTER TABLE skill_mastery ALTER COLUMN practice_count  SET DEFAULT 0;

-- ── wellness_state ────────────────────────────────────────────────
ALTER TABLE wellness_state ALTER COLUMN stress_level_30d              SET DEFAULT 0.3;
ALTER TABLE wellness_state ALTER COLUMN burnout_risk                  SET DEFAULT 0.0;
ALTER TABLE wellness_state ALTER COLUMN has_study_group              SET DEFAULT FALSE;
ALTER TABLE wellness_state ALTER COLUMN social_integration_score      SET DEFAULT 0.5;
ALTER TABLE wellness_state ALTER COLUMN family_pressure_level         SET DEFAULT 2;
ALTER TABLE wellness_state ALTER COLUMN home_study_environment_quality SET DEFAULT 'moderate';
ALTER TABLE wellness_state ALTER COLUMN intervention_status           SET DEFAULT 'pending';

-- ── digital_twin_predictions ──────────────────────────────────────
ALTER TABLE digital_twin_predictions ALTER COLUMN predicted_next_problem_correctness SET DEFAULT 0.5;
ALTER TABLE digital_twin_predictions ALTER COLUMN at_risk_probability                SET DEFAULT 0.3;
ALTER TABLE digital_twin_predictions ALTER COLUMN intervention_urgency               SET DEFAULT 'normal';
ALTER TABLE digital_twin_predictions ALTER COLUMN recommended_agent_type             SET DEFAULT 'coordinator';
ALTER TABLE digital_twin_predictions ALTER COLUMN confidence_score                   SET DEFAULT 0.5;
ALTER TABLE digital_twin_predictions ALTER COLUMN model_version                      SET DEFAULT 'baseline';

-- ── learning_progress ─────────────────────────────────────────────
ALTER TABLE learning_progress ALTER COLUMN problems_completed     SET DEFAULT 0;
ALTER TABLE learning_progress ALTER COLUMN problems_correct       SET DEFAULT 0;
ALTER TABLE learning_progress ALTER COLUMN language_support_level SET DEFAULT 'none';
ALTER TABLE learning_progress ALTER COLUMN chunking_size          SET DEFAULT 'medium';

COMMIT;

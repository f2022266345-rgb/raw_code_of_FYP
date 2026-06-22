-- ============================================================
-- Migration 004: Fix Digital Twin timestamp NOT NULL violations
-- ============================================================
-- Problem:
--   The Digital Twin tables were created via SQLAlchemy
--   Base.metadata.create_all() with PYTHON-side defaults
--   (default=_now_utc). Those defaults only fire on ORM inserts,
--   not on the raw `INSERT INTO ...` statements used by
--   digital_twin_router.py. Because the columns were created
--   NOT NULL with no DATABASE default, those raw inserts failed:
--     null value in column "created_at" of relation
--     "student_profiles" violates not-null constraint
--
-- Fix:
--   Add a database-level DEFAULT now() to every Digital Twin
--   timestamp column, and backfill any existing NULL rows.
--
-- Safe to run multiple times (idempotent).
-- ============================================================

BEGIN;

-- student_profiles -------------------------------------------------
ALTER TABLE student_profiles ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE student_profiles ALTER COLUMN updated_at SET DEFAULT now();
UPDATE student_profiles SET created_at = now() WHERE created_at IS NULL;
UPDATE student_profiles SET updated_at = now() WHERE updated_at IS NULL;

-- cognitive_state --------------------------------------------------
ALTER TABLE cognitive_state ALTER COLUMN last_updated SET DEFAULT now();
UPDATE cognitive_state SET last_updated = now() WHERE last_updated IS NULL;

-- wellness_state ---------------------------------------------------
ALTER TABLE wellness_state ALTER COLUMN updated_at SET DEFAULT now();
UPDATE wellness_state SET updated_at = now() WHERE updated_at IS NULL;

-- digital_twin_predictions ----------------------------------------
ALTER TABLE digital_twin_predictions ALTER COLUMN prediction_timestamp SET DEFAULT now();
UPDATE digital_twin_predictions SET prediction_timestamp = now() WHERE prediction_timestamp IS NULL;

-- learning_interactions -------------------------------------------
ALTER TABLE learning_interactions ALTER COLUMN interaction_timestamp SET DEFAULT now();
UPDATE learning_interactions SET interaction_timestamp = now() WHERE interaction_timestamp IS NULL;

-- learning_progress -----------------------------------------------
ALTER TABLE learning_progress ALTER COLUMN updated_at SET DEFAULT now();
UPDATE learning_progress SET updated_at = now() WHERE updated_at IS NULL;

COMMIT;

-- Verify the defaults are now set:
-- SELECT table_name, column_name, column_default
-- FROM information_schema.columns
-- WHERE column_name IN
--     ('created_at','updated_at','last_updated',
--      'prediction_timestamp','interaction_timestamp')
--   AND table_name IN
--     ('student_profiles','cognitive_state','wellness_state',
--      'digital_twin_predictions','learning_interactions','learning_progress')
-- ORDER BY table_name, column_name;

-- ============================================================
-- Migration 005: Fix skill_mastery BKT NOT NULL violations
-- ============================================================
-- Same root cause as migration 004: the BKT prior columns
-- (p_init, p_transit, p_guess, p_slip) were created NOT NULL
-- with Python-side ORM defaults only. The raw `INSERT INTO
-- skill_mastery ...` in services/digital_twin_updater.py did
-- not supply them, so PostgreSQL rejected the row:
--   null value in column "p_init" of relation "skill_mastery"
--   violates not-null constraint
--
-- Fix: give the columns database-level defaults (matching the
-- ORM defaults in db.py) and backfill any NULL rows.
--
-- Safe to run multiple times (idempotent).
-- ============================================================

BEGIN;

ALTER TABLE skill_mastery ALTER COLUMN p_mastery SET DEFAULT 0.2;
ALTER TABLE skill_mastery ALTER COLUMN p_init    SET DEFAULT 0.2;
ALTER TABLE skill_mastery ALTER COLUMN p_transit SET DEFAULT 0.1;
ALTER TABLE skill_mastery ALTER COLUMN p_guess   SET DEFAULT 0.25;
ALTER TABLE skill_mastery ALTER COLUMN p_slip    SET DEFAULT 0.05;

UPDATE skill_mastery SET p_init    = 0.2  WHERE p_init    IS NULL;
UPDATE skill_mastery SET p_transit = 0.1  WHERE p_transit IS NULL;
UPDATE skill_mastery SET p_guess   = 0.25 WHERE p_guess   IS NULL;
UPDATE skill_mastery SET p_slip    = 0.05 WHERE p_slip    IS NULL;

COMMIT;

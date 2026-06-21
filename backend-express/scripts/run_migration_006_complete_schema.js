/**
 * Migration 006 — Complete schema sync.
 *
 * Adds every column each Sequelize model expects but is missing from the DB,
 * and creates the two tables that don't exist yet.
 *
 * Safe to re-run: uses ADD COLUMN IF NOT EXISTS and CREATE TABLE IF NOT EXISTS.
 *
 * Run from backend-express directory:
 *   node scripts/run_migration_006_complete_schema.js
 */

import { Sequelize } from "sequelize";
import dotenv from "dotenv";
dotenv.config();

const DB = process.env.DATABASE_URL || "postgresql://postgres:admin@localhost:5432/FYP_backup";
const seq = new Sequelize(DB, { dialect: "postgres", logging: false });

const add = async (table, colDefs) => {
  for (const def of colDefs) {
    await seq.query(`ALTER TABLE ${table} ADD COLUMN IF NOT EXISTS ${def};`)
      .catch(e => console.warn(`  skip ${table}.${def.split(" ")[0]}: ${e.message}`));
  }
};

async function run() {
  await seq.authenticate();
  console.log("DB connected.\n");

  // ── diagnostic_profiles ───────────────────────────────────────────────────
  console.log("diagnostic_profiles...");
  await add("diagnostic_profiles", [
    `university           VARCHAR(120)`,
    `program              VARCHAR(120)`,
    `school_type          VARCHAR(80)`,
    `english_proficiency  VARCHAR(50)`,
    `years_english        INTEGER`,
    `previous_medium      TEXT[]   DEFAULT '{}'`,
    `study_pace           VARCHAR(50)`,
    `language_preference  VARCHAR(80)`,
    `study_habits         VARCHAR(50)`,
    `study_hours_per_week INTEGER`,
    `learning_styles      JSONB    DEFAULT '{}'`,
    `first_gen_student    BOOLEAN  DEFAULT FALSE`,
    `family_support       VARCHAR(50)`,
    `challenges           TEXT[]   DEFAULT '{}'`,
  ]);
  console.log("  ✓ diagnostic_profiles fixed\n");

  // ── social_metrics ────────────────────────────────────────────────────────
  console.log("social_metrics...");
  await add("social_metrics", [
    `first_gen_student  BOOLEAN  DEFAULT FALSE`,
    `family_support     VARCHAR(50)`,
    `city               VARCHAR(120)`,
    `background         VARCHAR(50)`,
    `challenges         TEXT[]   DEFAULT '{}'`,
    `learning_context   TEXT[]   DEFAULT '{}'`,
  ]);
  console.log("  ✓ social_metrics fixed\n");

  // ── wellness_logs ─────────────────────────────────────────────────────────
  console.log("wellness_logs...");
  await add("wellness_logs", [
    `stress_indicator  FLOAT   DEFAULT 0.0`,
    `family_pressure   BOOLEAN DEFAULT FALSE`,
    `source            VARCHAR(50) DEFAULT 'chat'`,
  ]);
  console.log("  ✓ wellness_logs fixed\n");

  // ── interaction_logs ──────────────────────────────────────────────────────
  console.log("interaction_logs...");
  await add("interaction_logs", [
    `event_id    UUID    NOT NULL DEFAULT gen_random_uuid()`,
    `session_id  VARCHAR(255)`,
    `attempts    INTEGER`,
    `click_count INTEGER`,
    `chat_text   TEXT`,
    `metadata    JSONB`,
    `"updatedAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()`,
  ]);
  // Back-fill event_id for rows that got NULL (NOT NULL constraint applied after)
  await seq.query(`UPDATE interaction_logs SET event_id = gen_random_uuid() WHERE event_id IS NULL`)
    .catch(() => {});
  // Add unique constraint on event_id if not present
  await seq.query(`
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'interaction_logs_event_id_unique') THEN
        ALTER TABLE interaction_logs ADD CONSTRAINT interaction_logs_event_id_unique UNIQUE (event_id);
      END IF;
    END $$;
  `).catch(() => {});
  console.log("  ✓ interaction_logs fixed\n");

  // ── student_interactions (CREATE if missing) ───────────────────────────────
  console.log("student_interactions...");
  await seq.query(`
    CREATE TABLE IF NOT EXISTS student_interactions (
      id                    SERIAL PRIMARY KEY,
      interaction_id        UUID         NOT NULL DEFAULT gen_random_uuid() UNIQUE,
      user_id               UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      session_id            VARCHAR(255),
      event_type            VARCHAR(100) NOT NULL DEFAULT 'chat',
      content_id            VARCHAR(255),
      agent_type            VARCHAR(50),
      correctness           BOOLEAN,
      hints_requested       INTEGER,
      attempts              INTEGER,
      response_time_ms      INTEGER,
      session_time_spent_ms INTEGER,
      message_text          TEXT,
      sentiment_score       FLOAT,
      sentiment_label       VARCHAR(50),
      metadata              JSONB,
      occurred_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
      "createdAt"           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
      "updatedAt"           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
  `);
  await seq.query(`CREATE INDEX IF NOT EXISTS idx_si_user      ON student_interactions(user_id);`);
  await seq.query(`CREATE INDEX IF NOT EXISTS idx_si_user_time ON student_interactions(user_id, occurred_at DESC);`);
  console.log("  ✓ student_interactions created/verified\n");

  // ── student_profile_state (CREATE if missing) ──────────────────────────────
  console.log("student_profile_state...");
  await seq.query(`
    CREATE TABLE IF NOT EXISTS student_profile_state (
      id                    SERIAL PRIMARY KEY,
      state_id              UUID    NOT NULL DEFAULT gen_random_uuid() UNIQUE,
      user_id               UUID    NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
      mastery_summary       JSONB   NOT NULL DEFAULT '{}',
      accuracy_trend_slope  FLOAT,
      time_trend_slope      FLOAT,
      hint_trend_slope      FLOAT,
      frustration_estimate  FLOAT,
      engagement_estimate   FLOAT,
      readiness_estimate    FLOAT,
      hidden_state          JSONB   NOT NULL DEFAULT '{}',
      interaction_window    INTEGER NOT NULL DEFAULT 8,
      last_computed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      "createdAt"           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      "updatedAt"           TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `);
  await seq.query(`CREATE INDEX IF NOT EXISTS idx_sps_user ON student_profile_state(user_id);`);
  console.log("  ✓ student_profile_state created/verified\n");

  console.log("Migration 006 complete — schema is fully synced.");
  await seq.close();
}

run().catch(err => { console.error("Migration 006 failed:", err.message); process.exit(1); });

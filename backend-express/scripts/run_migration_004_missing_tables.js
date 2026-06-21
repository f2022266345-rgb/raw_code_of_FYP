/**
 * Migration 004 — Create all missing tables.
 * Run from backend-express directory:
 *   node scripts/run_migration_004_missing_tables.js
 *
 * Tables created (only if they don't already exist):
 *   - initial_profiles
 *   - bkt_skill_mastery
 *   - interaction_logs
 *   - student_interactions
 *   - student_profile_state
 */

import { Sequelize, DataTypes } from "sequelize";
import dotenv from "dotenv";
dotenv.config();

const DATABASE_URL =
  process.env.DATABASE_URL ||
  "postgresql://postgres:admin@localhost:5432/FYP_backup";

const sequelize = new Sequelize(DATABASE_URL, { dialect: "postgres", logging: false });

async function run() {
  await sequelize.authenticate();
  console.log("DB connected.");

  // ── initial_profiles ─────────────────────────────────────────────────────
  await sequelize.query(`
    CREATE TABLE IF NOT EXISTS initial_profiles (
      id                     SERIAL PRIMARY KEY,
      "profileId"            UUID    NOT NULL DEFAULT gen_random_uuid() UNIQUE,
      persistent_learner_id  UUID,
      user_id                UUID    NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
      educational_background JSONB   NOT NULL DEFAULT '{}',
      learning_preferences   JSONB   NOT NULL DEFAULT '{}',
      cultural_context       JSONB   NOT NULL DEFAULT '{}',
      diagnostic_assessment  JSONB,
      user_profile           JSONB   NOT NULL DEFAULT '{}',
      ai_prediction          JSONB   NOT NULL DEFAULT '{}',
      bloom_level_predicted  INTEGER DEFAULT 1,
      bloom_level            INTEGER DEFAULT 1,
      language_barrier_risk  FLOAT   DEFAULT 0.2,
      learning_barriers_score FLOAT  DEFAULT 0.0,
      wellness_support_needed BOOLEAN DEFAULT FALSE,
      social_support_needed  BOOLEAN DEFAULT FALSE,
      academic_support_needed BOOLEAN DEFAULT TRUE,
      cognitive_rules        JSONB   DEFAULT '{}',
      active_agents          TEXT[]  DEFAULT ARRAY['academic'],
      requires_human_override BOOLEAN NOT NULL DEFAULT FALSE,
      "createdAt"            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      "updatedAt"            TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `);
  console.log("✓ initial_profiles");

  // ── bkt_skill_mastery ────────────────────────────────────────────────────
  await sequelize.query(`
    CREATE TABLE IF NOT EXISTS bkt_skill_mastery (
      id               SERIAL PRIMARY KEY,
      user_id          UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      skill_name       VARCHAR(200) NOT NULL,
      category         VARCHAR(100) DEFAULT 'General',
      p_mastery        FLOAT        NOT NULL DEFAULT 0.3,
      p_init           FLOAT,
      p_transit        FLOAT,
      p_guess          FLOAT,
      p_slip           FLOAT,
      p_forget         FLOAT,
      practice_count   INTEGER      NOT NULL DEFAULT 0,
      last_practiced_at TIMESTAMPTZ,
      "createdAt"      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
      "updatedAt"      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
      CONSTRAINT bkt_user_skill_unique UNIQUE (user_id, skill_name)
    );
    CREATE INDEX IF NOT EXISTS bkt_user_idx ON bkt_skill_mastery(user_id);
  `);
  console.log("✓ bkt_skill_mastery");

  // ── interaction_logs ─────────────────────────────────────────────────────
  await sequelize.query(`
    CREATE TABLE IF NOT EXISTS interaction_logs (
      id               SERIAL PRIMARY KEY,
      event_id         UUID        NOT NULL DEFAULT gen_random_uuid() UNIQUE,
      user_id          UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      session_id       VARCHAR(255),
      event_type       VARCHAR(100) NOT NULL,
      page_path        VARCHAR(255),
      correct          BOOLEAN,
      response_time_ms INTEGER,
      hints_used       INTEGER,
      attempts         INTEGER,
      time_on_page_ms  INTEGER,
      click_count      INTEGER,
      mood             VARCHAR(100),
      confidence_score FLOAT,
      chat_text        TEXT,
      sentiment_score  FLOAT,
      sentiment_label  VARCHAR(50),
      metadata         JSONB,
      occurred_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
      "createdAt"      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
      "updatedAt"      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_ilog_user      ON interaction_logs(user_id);
    CREATE INDEX IF NOT EXISTS idx_ilog_user_time ON interaction_logs(user_id, occurred_at DESC);
  `);
  console.log("✓ interaction_logs");

  // ── student_interactions ─────────────────────────────────────────────────
  await sequelize.query(`
    CREATE TABLE IF NOT EXISTS student_interactions (
      id                    SERIAL PRIMARY KEY,
      interaction_id        UUID         NOT NULL DEFAULT gen_random_uuid() UNIQUE,
      user_id               UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      session_id            VARCHAR(255),
      event_type            VARCHAR(100) NOT NULL,
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
    CREATE INDEX IF NOT EXISTS idx_si_user      ON student_interactions(user_id);
    CREATE INDEX IF NOT EXISTS idx_si_user_time ON student_interactions(user_id, occurred_at DESC);
  `);
  console.log("✓ student_interactions");

  // ── student_profile_state ────────────────────────────────────────────────
  await sequelize.query(`
    CREATE TABLE IF NOT EXISTS student_profile_state (
      id                   SERIAL PRIMARY KEY,
      state_id             UUID    NOT NULL DEFAULT gen_random_uuid() UNIQUE,
      user_id              UUID    NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
      mastery_summary      JSONB   NOT NULL DEFAULT '{}',
      accuracy_trend_slope FLOAT,
      time_trend_slope     FLOAT,
      hint_trend_slope     FLOAT,
      frustration_estimate FLOAT,
      engagement_estimate  FLOAT,
      readiness_estimate   FLOAT,
      hidden_state         JSONB   NOT NULL DEFAULT '{}',
      interaction_window   INTEGER NOT NULL DEFAULT 8,
      last_computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      "createdAt"          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      "updatedAt"          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_sps_user ON student_profile_state(user_id);
  `);
  console.log("✓ student_profile_state");

  console.log("\nMigration 004 complete — all missing tables created.");
  await sequelize.close();
}

run().catch((err) => {
  console.error("Migration 004 failed:", err.message);
  process.exit(1);
});

/**
 * Migration 005 — Fix initial_profiles schema.
 *
 * The table existed with an older schema (missing columns, wrong types).
 * This script adds missing columns and coerces column types to match
 * what the InitialProfile Sequelize model expects.
 *
 * Run from backend-express directory:
 *   node scripts/run_migration_005_fix_initial_profiles.js
 */

import { Sequelize } from "sequelize";
import dotenv from "dotenv";
dotenv.config();

const DATABASE_URL =
  process.env.DATABASE_URL ||
  "postgresql://postgres:admin@localhost:5432/FYP_backup";

const sequelize = new Sequelize(DATABASE_URL, { dialect: "postgres", logging: false });

async function run() {
  await sequelize.authenticate();
  console.log("DB connected.");

  // ── 1. Add missing columns (idempotent) ─────────────────────────────────
  const addCols = [
    `ALTER TABLE initial_profiles ADD COLUMN IF NOT EXISTS "profileId" UUID DEFAULT gen_random_uuid()`,
    `ALTER TABLE initial_profiles ADD COLUMN IF NOT EXISTS educational_background JSONB NOT NULL DEFAULT '{}'`,
    `ALTER TABLE initial_profiles ADD COLUMN IF NOT EXISTS cultural_context JSONB NOT NULL DEFAULT '{}'`,
    `ALTER TABLE initial_profiles ADD COLUMN IF NOT EXISTS diagnostic_assessment JSONB`,
    `ALTER TABLE initial_profiles ADD COLUMN IF NOT EXISTS bloom_level_predicted INTEGER DEFAULT 1`,
    `ALTER TABLE initial_profiles ADD COLUMN IF NOT EXISTS academic_support_needed BOOLEAN DEFAULT TRUE`,
  ];

  for (const sql of addCols) {
    await sequelize.query(sql);
  }
  console.log("✓ Missing columns added");

  // ── 2. Back-fill profileId for existing rows that got NULL ───────────────
  await sequelize.query(`
    UPDATE initial_profiles SET "profileId" = gen_random_uuid() WHERE "profileId" IS NULL
  `);
  console.log("✓ profileId back-filled");

  // ── 3. Add UNIQUE constraint on profileId (skip if already exists) ────────
  await sequelize.query(`
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'initial_profiles_profileId_unique'
      ) THEN
        ALTER TABLE initial_profiles ADD CONSTRAINT "initial_profiles_profileId_unique" UNIQUE ("profileId");
      END IF;
    END
    $$;
  `);
  console.log("✓ profileId unique constraint added");

  // ── 4. Fix column types ──────────────────────────────────────────────────

  // persistent_learner_id: VARCHAR → UUID
  await sequelize.query(`
    ALTER TABLE initial_profiles
      ALTER COLUMN persistent_learner_id TYPE UUID
      USING CASE
        WHEN persistent_learner_id IS NULL THEN NULL
        WHEN persistent_learner_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
          THEN persistent_learner_id::UUID
        ELSE NULL
      END;
  `).catch((e) => console.warn("persistent_learner_id type already correct or skipped:", e.message));

  // JSON columns → JSONB
  for (const col of ["learning_preferences", "user_profile", "ai_prediction", "cognitive_rules"]) {
    await sequelize.query(`
      ALTER TABLE initial_profiles ALTER COLUMN ${col} TYPE JSONB USING ${col}::JSONB;
    `).catch((e) => console.warn(`${col} type already correct or skipped:`, e.message));
  }

  // active_agents: JSON → TEXT[]
  await sequelize.query(`
    ALTER TABLE initial_profiles
      ALTER COLUMN active_agents TYPE TEXT[]
      USING CASE
        WHEN active_agents IS NULL THEN ARRAY['academic']::TEXT[]
        ELSE ARRAY(SELECT jsonb_array_elements_text(active_agents::JSONB))
      END;
  `).catch((e) => console.warn("active_agents type already correct or skipped:", e.message));

  console.log("✓ Column types fixed");
  console.log("\nMigration 005 complete.");
  await sequelize.close();
}

run().catch((err) => {
  console.error("Migration 005 failed:", err.message);
  process.exit(1);
});

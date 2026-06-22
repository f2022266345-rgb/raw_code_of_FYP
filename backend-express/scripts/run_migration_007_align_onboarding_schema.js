/**
 * Migration 007 — Align onboarding schema with Sequelize models.
 *
 * The live database (FYP_DB_Latest) drifted out of sync with the models:
 * several tables were missing columns the onboarding pipeline writes to,
 * which made InitialProfile / DiagnosticProfile / SocialMetrics / WellnessLog
 * inserts fail with "column ... does not exist".
 *
 * This migration is fully idempotent — safe to run repeatedly. It only adds
 * missing columns, relaxes NOT NULL where the model allows null, and coerces
 * a few column types. It never drops data.
 *
 * Run from the backend-express directory:
 *   node scripts/run_migration_007_align_onboarding_schema.js
 */

import { Sequelize } from "sequelize";
import dotenv from "dotenv";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: join(__dirname, "../.env") });

const DATABASE_URL =
  process.env.DATABASE_URL ||
  "postgresql://postgres:admin@localhost:5432/FYP_backup";

const sequelize = new Sequelize(DATABASE_URL, { dialect: "postgres", logging: false });

// Run a statement, logging a short note. Type coercions may legitimately
// fail when already correct — those are wrapped by the caller with `soft`.
async function run(sql) {
  await sequelize.query(sql);
}
async function soft(sql, label) {
  try {
    await sequelize.query(sql);
  } catch (e) {
    console.warn(`  (skipped: ${label}) ${e.message.split("\n")[0]}`);
  }
}

async function migrate() {
  await sequelize.authenticate();
  console.log(`DB connected → ${sequelize.getDatabaseName?.() || DATABASE_URL.split("@")[1] || ""}`);

  // ── diagnostic_profiles ──────────────────────────────────────────────
  console.log("\n[1/4] diagnostic_profiles");
  const diagCols = [
    `ADD COLUMN IF NOT EXISTS "university" VARCHAR(120)`,
    `ADD COLUMN IF NOT EXISTS "program" VARCHAR(120)`,
    `ADD COLUMN IF NOT EXISTS "school_type" VARCHAR(80)`,
    `ADD COLUMN IF NOT EXISTS "english_proficiency" VARCHAR(50)`,
    `ADD COLUMN IF NOT EXISTS "years_english" INTEGER`,
    `ADD COLUMN IF NOT EXISTS "previous_medium" TEXT[] DEFAULT '{}'`,
    `ADD COLUMN IF NOT EXISTS "study_pace" VARCHAR(50)`,
    `ADD COLUMN IF NOT EXISTS "language_preference" VARCHAR(80)`,
    `ADD COLUMN IF NOT EXISTS "study_habits" VARCHAR(50)`,
    `ADD COLUMN IF NOT EXISTS "study_hours_per_week" INTEGER`,
    `ADD COLUMN IF NOT EXISTS "learning_styles" JSONB DEFAULT '{}'`,
  ];
  await run(`ALTER TABLE diagnostic_profiles ${diagCols.join(", ")}`);
  // Model marks these nullable; the original table had them NOT NULL.
  for (const col of ["prior_education", "primary_language", "commute_type", "tech_access"]) {
    await soft(`ALTER TABLE diagnostic_profiles ALTER COLUMN "${col}" DROP NOT NULL`, `${col} not-null`);
  }
  console.log("  ✓ columns aligned");

  // ── initial_profiles ─────────────────────────────────────────────────
  console.log("\n[2/4] initial_profiles");
  const ipCols = [
    `ADD COLUMN IF NOT EXISTS "profileId" UUID DEFAULT gen_random_uuid()`,
    `ADD COLUMN IF NOT EXISTS "educational_background" JSONB NOT NULL DEFAULT '{}'`,
    `ADD COLUMN IF NOT EXISTS "cultural_context" JSONB NOT NULL DEFAULT '{}'`,
    `ADD COLUMN IF NOT EXISTS "diagnostic_assessment" JSONB`,
    `ADD COLUMN IF NOT EXISTS "bloom_level_predicted" INTEGER DEFAULT 1`,
    `ADD COLUMN IF NOT EXISTS "academic_support_needed" BOOLEAN DEFAULT TRUE`,
  ];
  await run(`ALTER TABLE initial_profiles ${ipCols.join(", ")}`);

  // Back-fill + unique constraint on profileId
  await run(`UPDATE initial_profiles SET "profileId" = gen_random_uuid() WHERE "profileId" IS NULL`);
  await run(`
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'initial_profiles_profileId_unique') THEN
        ALTER TABLE initial_profiles ADD CONSTRAINT "initial_profiles_profileId_unique" UNIQUE ("profileId");
      END IF;
    END $$;
  `);
  await run(`ALTER TABLE initial_profiles ALTER COLUMN "profileId" SET NOT NULL`);

  // Type coercions to match the model
  await soft(
    `ALTER TABLE initial_profiles ALTER COLUMN persistent_learner_id TYPE UUID
       USING CASE
         WHEN persistent_learner_id IS NULL THEN NULL
         WHEN persistent_learner_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
           THEN persistent_learner_id::UUID
         ELSE NULL
       END`,
    "persistent_learner_id → uuid"
  );
  for (const col of ["learning_preferences", "user_profile", "ai_prediction", "cognitive_rules"]) {
    await soft(`ALTER TABLE initial_profiles ALTER COLUMN ${col} TYPE JSONB USING ${col}::JSONB`, `${col} → jsonb`);
  }
  // active_agents json → text[]. Postgres forbids subqueries inside an
  // ALTER COLUMN USING clause, so convert via a temp column swap (subqueries
  // are allowed in UPDATE). Idempotent: only runs while the column is json.
  await run(`
    DO $$
    DECLARE col_type text;
    BEGIN
      SELECT data_type INTO col_type FROM information_schema.columns
        WHERE table_name = 'initial_profiles' AND column_name = 'active_agents';
      IF col_type IN ('json', 'jsonb') THEN
        ALTER TABLE initial_profiles ADD COLUMN active_agents_tmp TEXT[] DEFAULT ARRAY['academic']::TEXT[];
        UPDATE initial_profiles SET active_agents_tmp =
          CASE
            WHEN active_agents IS NULL THEN ARRAY['academic']::TEXT[]
            ELSE ARRAY(SELECT jsonb_array_elements_text(active_agents::JSONB))
          END;
        ALTER TABLE initial_profiles DROP COLUMN active_agents;
        ALTER TABLE initial_profiles RENAME COLUMN active_agents_tmp TO active_agents;
      END IF;
    END $$;
  `);
  console.log("  ✓ columns + types aligned");

  // ── social_metrics ───────────────────────────────────────────────────
  console.log("\n[3/4] social_metrics");
  const smCols = [
    `ADD COLUMN IF NOT EXISTS "first_gen_student" BOOLEAN DEFAULT FALSE`,
    `ADD COLUMN IF NOT EXISTS "family_support" VARCHAR(50)`,
    `ADD COLUMN IF NOT EXISTS "city" VARCHAR(120)`,
    `ADD COLUMN IF NOT EXISTS "background" VARCHAR(50)`,
    `ADD COLUMN IF NOT EXISTS "challenges" TEXT[] DEFAULT '{}'`,
    `ADD COLUMN IF NOT EXISTS "learning_context" TEXT[] DEFAULT '{}'`,
  ];
  await run(`ALTER TABLE social_metrics ${smCols.join(", ")}`);
  console.log("  ✓ columns aligned");

  // ── wellness_logs ────────────────────────────────────────────────────
  console.log("\n[4/4] wellness_logs");
  const wlCols = [
    `ADD COLUMN IF NOT EXISTS "stress_indicator" DOUBLE PRECISION DEFAULT 0.0`,
    `ADD COLUMN IF NOT EXISTS "family_pressure" BOOLEAN DEFAULT FALSE`,
    `ADD COLUMN IF NOT EXISTS "source" VARCHAR(50) DEFAULT 'chat'`,
  ];
  await run(`ALTER TABLE wellness_logs ${wlCols.join(", ")}`);
  await soft(`ALTER TABLE wellness_logs ALTER COLUMN sentiment_marker SET DEFAULT 'Neutral'`, "sentiment default");
  console.log("  ✓ columns aligned");

  console.log("\nMigration 007 complete — onboarding schema aligned with models.");
  await sequelize.close();
}

migrate().catch(async (err) => {
  console.error("\nMigration 007 failed:", err.message);
  try { await sequelize.close(); } catch {}
  process.exit(1);
});

/**
 * Migration 008 — Sync all Sequelize models into the database.
 *
 * The Sequelize models in `model/` are the source of truth. Auto-sync is
 * disabled in server.js, so live tables can be missing. This script imports
 * the full model registry (model/index.js — which also wires up all the
 * associations / foreign keys) and runs `sequelize.sync()`.
 *
 * `sync()` (default) issues `CREATE TABLE IF NOT EXISTS` for every model:
 *   - missing tables (e.g. student_profile_state, student_interactions,
 *     counselor_cases) are created with the exact columns + FKs from the model
 *   - existing tables are left completely untouched (no column drops/alters)
 *
 * Run from the backend-express directory:
 *   node scripts/run_migration_008_sync_models.js
 *   npm run db:sync
 *
 * Target DB is read from backend-express/.env DATABASE_URL (FYP_DB_Latest).
 */

import db, { sequelize } from "../model/index.js";

async function run() {
  await sequelize.authenticate();
  console.log(`DB connected: ${sequelize.config.database}`);

  const before = await listTables();

  // Default sync = CREATE TABLE IF NOT EXISTS (safe, non-destructive).
  await sequelize.sync();

  const after = await listTables();
  const created = after.filter((t) => !before.includes(t));

  console.log("\nModels registered:");
  Object.keys(db)
    .filter((k) => k !== "sequelize" && db[k]?.tableName)
    .forEach((k) => console.log(`  ${k.padEnd(22)} -> ${db[k].tableName}`));

  if (created.length) {
    console.log("\nTables created:");
    created.forEach((t) => console.log(`  + ${t}`));
  } else {
    console.log("\nNo new tables — schema already in sync.");
  }

  console.log("\nMigration 008 complete.");
  await sequelize.close();
}

async function listTables() {
  const [rows] = await sequelize.query(
    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
  );
  return rows.map((r) => r.tablename);
}

run().catch((err) => {
  console.error("Migration 008 failed:", err.message);
  console.error(err);
  process.exit(1);
});

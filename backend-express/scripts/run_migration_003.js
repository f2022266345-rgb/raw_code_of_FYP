/**
 * Migration 003 — Run from backend-express directory:
 *   node scripts/run_migration_003.js
 *
 * Adds agent_type column to episodic_memory table in FastAPI DB
 * so each agent's vector memories are stored separately.
 */

import { Sequelize } from "sequelize";
import dotenv from "dotenv";
dotenv.config();

const DATABASE_URL =
  process.env.DATABASE_URL ||
  "postgresql://postgres:admin@localhost:5432/FYP_backup";

const sequelize = new Sequelize(DATABASE_URL, { dialect: "postgres", logging: false });

async function run() {
  try {
    await sequelize.authenticate();
    console.log("DB connected.");

    await sequelize.query(`
      ALTER TABLE episodic_memory
        ADD COLUMN IF NOT EXISTS agent_type VARCHAR(20) DEFAULT NULL;
    `);
    console.log("Column agent_type added to episodic_memory.");

    await sequelize.query(`
      CREATE INDEX IF NOT EXISTS idx_episodic_user_agent
        ON episodic_memory(user_id, agent_type);
    `);
    console.log("Index idx_episodic_user_agent created.");

    console.log("Migration 003 complete.");
  } catch (err) {
    console.error("Migration 003 failed:", err.message);
  } finally {
    await sequelize.close();
  }
}

run();

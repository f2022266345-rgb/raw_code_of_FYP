import pg from "pg";
import dotenv from "dotenv";

dotenv.config();

const client = new pg.Client({ connectionString: process.env.DATABASE_URL });
await client.connect();

const tables = await client.query(`
  SELECT table_name
  FROM information_schema.tables
  WHERE table_schema = 'public'
  ORDER BY table_name
`);

console.log("Tables:");
for (const row of tables.rows) {
  console.log(` - ${row.table_name}`);
}

const core = [
  "users",
  "diagnostic_profiles",
  "academic_progress",
  "social_metrics",
  "wellness_logs",
  "chat_threads",
  "chat_messages",
];

const present = new Set(tables.rows.map((r) => r.table_name));
const missing = core.filter((t) => !present.has(t));
console.log(missing.length ? `Missing: ${missing.join(", ")}` : "All 7 core tables present.");

await client.end();

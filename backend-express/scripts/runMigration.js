import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import pg from "pg";
import dotenv from "dotenv";

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const migrationPath = path.join(
  __dirname,
  "..",
  "migrations",
  "001_lumina_core_schema.sql",
);

const databaseUrl = process.env.DATABASE_URL;
if (!databaseUrl) {
  console.error("DATABASE_URL is required in backend_express/.env");
  process.exit(1);
}

const sql = fs.readFileSync(migrationPath, "utf8");

const client = new pg.Client({ connectionString: databaseUrl });

try {
  await client.connect();
  console.log(`Connected to ${databaseUrl.replace(/:[^:@]+@/, ":****@")}`);
  await client.query(sql);
  console.log("Migration 001_lumina_core_schema.sql applied successfully.");
} catch (error) {
  console.error("Migration failed:", error.message);
  process.exit(1);
} finally {
  await client.end();
}

import { Sequelize } from "sequelize";
import dotenv from "dotenv";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

// Load .env from backend-express/ using an absolute path so it works
// regardless of which directory the server process is started from.
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
dotenv.config({ path: join(__dirname, "../.env") });

const databaseUrl = process.env.DATABASE_URL;

const sequelize = databaseUrl
  ? new Sequelize(databaseUrl, {
      dialect: "postgres",
      logging: false,
    })
  : new Sequelize(
      process.env.DB_NAME    || "FYP_backup",
      process.env.DB_USER    || "postgres",
      String(process.env.DB_PASSWORD || "admin"),
      {
        host:    process.env.DB_HOST || "localhost",
        port:    Number(process.env.DB_PORT) || 5432,
        dialect: "postgres",
        logging: false,
      },
    );

export { sequelize };

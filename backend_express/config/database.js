import { Sequelize } from "sequelize";
import dotenv from "dotenv";

dotenv.config();

// Option 1: Use a single connection string (Best for Production/Docker)
// Example: postgres://user:pass@localhost:5432/dbname
const databaseUrl = process.env.DATABASE_URL;

const sequelize = databaseUrl
  ? new Sequelize(databaseUrl, {
      dialect: "postgres",
      logging: false, // Set to console.log to see SQL queries
    })
  : new Sequelize(
      process.env.DB_NAME || "postgres",
      process.env.DB_USER || "postgres",
      String(process.env.DB_PASSWORD || ""),
      {
        host: process.env.DB_HOST || "localhost",
        port: Number(process.env.DB_PORT) || 5432,
        dialect: "postgres",
        logging: false,
      },
    );

export { sequelize };

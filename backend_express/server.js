import express from "express";
import { sequelize } from "./config/database.js";
import cors from "cors";
import dotenv from "dotenv";
import AuthRoutes from "./routes/authRoutes.js";
import OnboardingRoutes from "./routes/OnboardingRoutes.js";
import DashboardRoutes from "./routes/dashboardRoutes.js";
import ObservationsRoutes from "./routes/observationsRoutes.js";
import BktRoutes from "./routes/bktRoutes.js";
import ChatRoutes from "./routes/chatRoutes.js";

dotenv.config();

const app = express();
const PORT = Number(process.env.PORT) || 4000;

const corsOptions = {
  origin: process.env.FRONTEND_URL || "http://localhost:3000",
  methods: ["GET", "POST", "PUT", "DELETE", "PATCH"],
  allowedHeaders: ["Content-Type", "Authorization"],
  credentials: true,
};

app.use(cors(corsOptions));
app.use(express.json());

// http://localhost:4000/api/dashboard/login
// Auth
app.use("/api/auth", AuthRoutes);

// Onboarding (correct spelling + legacy typo alias for backward-compat)
app.use("/api/initial-profiling", OnboardingRoutes);
app.use("/api/intitalproflling", OnboardingRoutes); // legacy alias — keep until frontend updated

// Dashboard
app.use("/api/dashboard", DashboardRoutes);

// Observations
app.use("/api/observations", ObservationsRoutes);

// BKT Skill Mastery
app.use("/api/bkt", BktRoutes);

// AI Agent Chat
app.use("/api/chat", ChatRoutes);

app.get("/", (_req, res) => {
  res.json({ message: "AI Academy Backend is running", version: "2.0.0" });
});

app.get("/health", async (_req, res) => {
  try {
    await sequelize.authenticate();
    return res.status(200).json({ status: "ok", database: "connected" });
  } catch (error) {
    return res.status(500).json({
      status: "error",
      database: "disconnected",
      message: error.message,
    });
  }
});

/**
 * Handles legacy schema drift where bkt_skill_mastery.user_id was created as VARCHAR.
 * The FK to users.userId requires UUID on both sides.
 */
async function normalizeLegacyBktUserIdColumn() {
  const [rows] = await sequelize.query(`
    SELECT data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'bkt_skill_mastery'
      AND column_name = 'user_id'
    LIMIT 1;
  `);

  if (!rows?.length) {
    return;
  }

  const currentType = rows[0].data_type;
  if (currentType === "uuid") {
    return;
  }

  if (currentType === "character varying" || currentType === "text") {
    console.log(
      "Database: Normalizing bkt_skill_mastery.user_id from text to UUID...",
    );

    await sequelize.query(
      `ALTER TABLE "bkt_skill_mastery" DROP CONSTRAINT IF EXISTS "bkt_skill_mastery_user_id_fkey";`,
    );

    // Remove legacy rows that cannot be cast to UUID.
    await sequelize.query(`
      DELETE FROM "bkt_skill_mastery"
      WHERE "user_id" IS NULL
         OR "user_id" !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$';
    `);

    await sequelize.query(`
      ALTER TABLE "bkt_skill_mastery"
      ALTER COLUMN "user_id" TYPE UUID
      USING "user_id"::uuid;
    `);
  }
}

/**
 * Starts the Express server after ensuring Database connectivity.
 */
async function startServer() {
  const BORDER = "------------------------------------------";

  try {
    console.log("\n🚀 Initializing AI Academy Backend v2.0...");

    await sequelize.authenticate();

    await normalizeLegacyBktUserIdColumn();

    // alter: true safely adds new columns without dropping existing data
    await sequelize.sync({ alter: true });

    console.log("Database: PostgreSQL connection established.");
    console.log("Database: Schema synced (alter mode).");

    const server = app.listen(PORT, () => {
      console.log(`
${BORDER}
✅ SERVER IS LIVE
📱 URL: http://localhost:${PORT}
🛠️  Environment: ${process.env.NODE_ENV || "development"}
📚 BKT endpoint: /api/bkt/skills
💬 Chat endpoint: /api/chat
${BORDER}
      `);
    });

    process.on("SIGTERM", () => {
      console.log("Shutting down gracefully...");
      server.close(() => process.exit(0));
    });
  } catch (error) {
    console.error(`
${BORDER}
❌ STARTUP ERROR
Critical failure during server boot.
Reason: ${error.message}
${BORDER}
    `);
    process.exit(1);
  }
}

startServer();

// @file:AGENTS.md

// what you have to do you have to go to the Fyp_project you have to refine the UI the front page / route is good and everything in it also good but refine the ui make the additional pages
// only these pages include

// Home
// Services -> drop down (agent etc add what you like to add)
// About
// Contact Us

// all the pricing ui remove

// and also change the ui of sign in sign up page add forgot password functionality from forntend to express_backend

// then if the user is first time login then a forn show now what you have to do to to the form is that the form is good change its ui to match the theme of my website but the payload and the field remain as it is as it is now becuase my bakcend expect this payload to parse

// and then on the dashbaord you have to change the ui

// main thing is that all the website have same theme use no other ui get it

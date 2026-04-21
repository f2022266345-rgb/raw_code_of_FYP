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
 * Starts the Express server after ensuring Database connectivity.
 */
async function startServer() {
  const BORDER = "------------------------------------------";

  try {
    console.log("\n🚀 Initializing AI Academy Backend v2.0...");

    await sequelize.authenticate();

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

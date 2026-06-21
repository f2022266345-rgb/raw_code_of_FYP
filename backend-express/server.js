import express from "express";
import dotenv from "dotenv";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

// Resolve .env from the backend-express directory using an absolute path
// so the server works regardless of which directory it's launched from.
const __filename = fileURLToPath(import.meta.url);
const __dirname  = dirname(__filename);
dotenv.config({ path: join(__dirname, ".env") });

import { sequelize } from "./config/database.js";
import cors from "cors";
import { initializeClerkMiddleware, requireAuth } from "./middlewares/clerkMiddleware.js";
import OnboardingRoutes from "./routes/OnboardingRoutes.js";
import DashboardRoutes from "./routes/dashboardRoutes.js";
import ObservationsRoutes from "./routes/observationsRoutes.js";
import BktRoutes from "./routes/bktRoutes.js";
import ChatRoutes from "./routes/chatRoutes.js";
import WebhookRoutes from "./routes/webhookRoutes.js";
import ClerkAuthRoutes from "./routes/clerkAuthRoutes.js";
import CounselorRoutes from "./routes/counselorRoutes.js";
import DigitalTwinRoutes from "./routes/digitalTwinRoutes.js";
import "./services/cronJobs.js";

dotenv.config();

const app = express();
const PORT = Number(process.env.PORT) || 4000;

const allowedOrigin = process.env.FRONTEND_URL && process.env.FRONTEND_URL !== "*"
  ? process.env.FRONTEND_URL
  : "http://localhost:3000";

const corsOptions = {
  origin: allowedOrigin,
  methods: ["GET", "POST", "PUT", "DELETE", "PATCH"],
  allowedHeaders: ["Content-Type", "Authorization"],
  credentials: true,
};

app.use(cors(corsOptions));

// Clerk webhook route - needs raw body for signature verification
app.post(
  "/api/webhooks/clerk",
  express.raw({ type: "application/json" }),
  WebhookRoutes
);

// All other routes use JSON parsing
app.use(express.json());

// Initialize Clerk middleware for token verification on all routes
app.use(initializeClerkMiddleware());

// All authentication is now handled by Clerk
app.use("/api/auth/clerk", ClerkAuthRoutes);
app.use("/api/initial-profiling", requireAuth, OnboardingRoutes);
app.use("/api/dashboard", requireAuth, DashboardRoutes);
app.use("/api/observations", requireAuth, ObservationsRoutes);
app.use("/api/bkt", requireAuth, BktRoutes);
app.use("/api/chat", requireAuth, ChatRoutes);
app.use("/api/counselor", requireAuth, CounselorRoutes);
app.use("/api/digital-twin", DigitalTwinRoutes);

app.get("/", (_req, res) => {
  res.json({ message: "AI Academy Backend is running", version: "3.0.0" });
});

app.get("/health", async (_req, res) => {
  try {
    await sequelize.authenticate();
    return res.status(200).json({ status: "ok", database: "connected", schema: "lumina_v2" });
  } catch (error) {
    return res.status(500).json({
      status: "error",
      database: "disconnected",
      message: error.message,
    });
  }
});

async function connectWithRetry(retries = 8, delayMs = 3000) {
  for (let i = 1; i <= retries; i++) {
    try {
      await sequelize.authenticate();
      return;
    } catch (err) {
      const isRecovery =
        err.message.includes("recovery mode") ||
        err.message.includes("starting up") ||
        err.message.includes("ECONNREFUSED");
      if (isRecovery && i < retries) {
        console.log(`Database not ready yet (${err.message.split("\n")[0]}). Retrying ${i}/${retries} in ${delayMs / 1000}s...`);
        await new Promise((res) => setTimeout(res, delayMs));
      } else {
        throw err;
      }
    }
  }
}

async function startServer() {
  const BORDER = "------------------------------------------";

  try {
    console.log("\nInitializing Lumina Express Backend v3.0...");

    await connectWithRetry();

    console.log("Database: PostgreSQL connection established.");
    console.log("Database: Automatic schema syncing disabled. Run migrations manually.");

    const server = app.listen(PORT, () => {
      console.log(`
${BORDER}
SERVER IS LIVE
URL: http://localhost:${PORT}
Environment: ${process.env.NODE_ENV || "development"}
Chat endpoint: /api/chat
Migration: npm run db:migrate
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
STARTUP ERROR
Reason: ${error.message}
${BORDER}
    `);
    process.exit(1);
  }
}

startServer();

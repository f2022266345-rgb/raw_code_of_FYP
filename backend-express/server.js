import express from "express";
import { sequelize } from "./config/database.js";
import cors from "cors";
import dotenv from "dotenv";
import { initializeClerkMiddleware, requireAuth } from "./middlewares/clerkMiddleware.js";
import OnboardingRoutes from "./routes/OnboardingRoutes.js";
import DashboardRoutes from "./routes/dashboardRoutes.js";
import ObservationsRoutes from "./routes/observationsRoutes.js";
import BktRoutes from "./routes/bktRoutes.js";
import ChatRoutes from "./routes/chatRoutes.js";
import WebhookRoutes from "./routes/webhookRoutes.js";
import ClerkAuthRoutes from "./routes/clerkAuthRoutes.js";

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

async function startServer() {
  const BORDER = "------------------------------------------";

  try {
    console.log("\nInitializing Lumina Express Backend v3.0...");

    await sequelize.authenticate();
    await sequelize.sync({ alter: true });

    console.log("Database: PostgreSQL connection established.");
    console.log("Database: Lumina core schema synced (alter mode).");

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

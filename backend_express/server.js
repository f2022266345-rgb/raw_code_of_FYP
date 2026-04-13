import express from "express";
import { sequelize } from "./config/database.js";
import cors from "cors";
import dotenv from "dotenv";
import AuthRoutes from "./routes/authRoutes.js";
import OnboardingRoutes from "./routes/OnboardingRoutes.js";
import DashboardRoutes from "./routes/dashboardRoutes.js";
import ObservationsRoutes from "./routes/observationsRoutes.js";

dotenv.config();

const app = express();
const PORT = Number(process.env.PORT) || 3000;

const corsOptions = {
  // Allow your frontend URL
  origin: "http://localhost:3000",
  methods: ["GET", "POST", "PUT", "DELETE", "PATCH"],
  // This is the important part: allow Authorization header
  allowedHeaders: ["Content-Type", "Authorization"],
  credentials: true,
};

app.use(cors(corsOptions));

app.use(express.json());

app.use("/api/auth", AuthRoutes);
app.use("/api/onboarding", OnboardingRoutes);
app.use("/api/intitalproflling", OnboardingRoutes);
app.use("/api/dashboard", DashboardRoutes);
app.use("/api/observations", ObservationsRoutes);
app.get("/", (_req, res) => {
  res.json({ message: "Backend is running" });
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
 * Starts the Express server after ensuring Database connectivity
 */
async function startServer() {
  const BORDER = "------------------------------------------";

  try {
    console.log("\n🚀 Initializing AI Academy Backend...");

    // 1. Database Connection
    await sequelize.authenticate();

    // 2. Sync Models (Consider { alter: true } for dev, but be careful in prod)
    await sequelize.sync();

    console.log("Database: PostgreSQL connection established.");

    // 3. Start Listening
    const server = app.listen(PORT, () => {
      console.log(`
${BORDER}
✅ SERVER IS LIVE
📱 URL: http://localhost:${PORT}
🛠️  Environment: ${process.env.NODE_ENV || "development"}
${BORDER}
      `);
    });

    // Handle sudden shutdowns gracefully
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

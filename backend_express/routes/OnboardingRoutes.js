import express from "express";
import onboardingController from "../controllers/onboardingControllers.js";
import { requireAuth } from "../middlewares/authMiddleware.js";

const router = express.Router();

// Define clean, readable routes
router.post("/", requireAuth, onboardingController);

export default router;

import express from "express";
import onboardingController from "../controllers/onboardingControllers.js";

const router = express.Router();

// requireAuth is already applied at the server.js mount level
router.post("/", onboardingController);

export default router;

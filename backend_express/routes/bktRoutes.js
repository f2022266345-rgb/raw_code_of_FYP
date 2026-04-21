import express from "express";
import bktController from "../controllers/bktController.js";
import { requireAuth } from "../middlewares/authMiddleware.js";

const router = express.Router();

// Get all BKT skills and mastery levels for the authenticated user
router.get("/skills", requireAuth, bktController.getUserSkills);

// Update a single skill's mastery after a learning interaction
router.post("/skills/:skillName/update", requireAuth, bktController.updateSkillMastery);

// Analyze current cognitive state from recent interaction logs
router.get("/state", requireAuth, bktController.analyzeState);

export default router;

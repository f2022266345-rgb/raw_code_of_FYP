import express from "express";
import bktController from "../controllers/bktController.js";

const router = express.Router();

// requireAuth is applied at the server.js mount level — no need to repeat it here

// Get all BKT skills and mastery levels for the authenticated user
router.get("/skills", bktController.getUserSkills);

// Update a single skill's mastery after a learning interaction
router.post("/skills/:skillName/update", bktController.updateSkillMastery);

// Analyze current cognitive state from recent interaction logs
router.get("/state", bktController.analyzeState);

export default router;

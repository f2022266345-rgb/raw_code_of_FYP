import { Router } from "express";
import counselorController from "../controllers/counselorController.js";

const router = Router();

// Dashboard overview
router.get("/stats", counselorController.getDashboardStats);

// Case management
router.get("/overrides", counselorController.getOverrides);
router.post("/resolve-override/:userId", counselorController.resolveOverride);
router.get("/cases", counselorController.listCases);
router.post("/cases", counselorController.createCase);
router.get("/cases/:caseId", counselorController.getCase);
router.patch("/cases/:caseId", counselorController.updateCase);

export default router;

import express from "express";
import digitalTwinController from "../controllers/digitalTwinController.js";
import { requireAuth } from "../middlewares/clerkMiddleware.js";

const router = express.Router();

router.use(requireAuth);

// Get student's digital twin
router.get(
  "/student",
  (req, res) => digitalTwinController.getStudentTwin(req, res)
);

// Update twin with a new interaction
router.post(
  "/update",
  (req, res) => digitalTwinController.updateTwin(req, res)
);

// Get analytics (query param: ?period=7d|30d|90d)
router.get(
  "/analytics",
  (req, res) => digitalTwinController.getAnalytics(req, res)
);

// Initialize twin during onboarding
router.post(
  "/initialize",
  (req, res) => digitalTwinController.initializeTwin(req, res)
);

export default router;

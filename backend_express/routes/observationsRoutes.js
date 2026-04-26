import express from "express";
import observationsController from "../controllers/observationsController.js";
import { requireAuth } from "../middlewares/authMiddleware.js";

const router = express.Router();

router.post("/log", requireAuth, observationsController.logObservation);
router.post("/batch", requireAuth, observationsController.logObservationBatch);
router.post("/hint", requireAuth, observationsController.logHintRequested);
router.get(
  "/summary",
  requireAuth,
  observationsController.getObservationSummary,
);

export default router;

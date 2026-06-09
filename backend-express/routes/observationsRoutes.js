import express from "express";
import observationsController from "../controllers/observationsController.js";

const router = express.Router();

// requireAuth is applied at the server.js mount level — no need to repeat it here
router.post("/log", observationsController.logObservation);
router.post("/batch", observationsController.logObservationBatch);
router.post("/hint", observationsController.logHintRequested);
router.get("/summary", observationsController.getObservationSummary);

export default router;

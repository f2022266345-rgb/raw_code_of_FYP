import express from "express";
import dashboardController from "../controllers/dashboardController.js";
import { requireAuth } from "../middlewares/authMiddleware.js";

const router = express.Router();

router.get("/", requireAuth, dashboardController.getMyDashboard);
router.get("/me", requireAuth, dashboardController.getMyDashboard);

export default router;

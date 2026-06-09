import express from "express";
import dashboardController from "../controllers/dashboardController.js";

const router = express.Router();

// requireAuth is applied at the server.js mount level — no need to repeat it here
router.get("/", dashboardController.getMyDashboard);
router.get("/me", dashboardController.getMyDashboard);

export default router;

import express from "express";
import authController from "../controllers/authControllers.js";

const router = express.Router();

// Define clean, readable routes
router.post("/login", authController.login);
router.post("/signup", authController.signup);
// router.get("/logout", authController.logout); // Optional: Implement logout logic if needed
router.get("/token", authController.token);
export default router;

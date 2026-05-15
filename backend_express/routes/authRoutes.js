import express from "express";
import authController from "../controllers/authControllers.js";

const router = express.Router();

// Define clean, readable routes
router.post("/login", authController.login);
router.post("/signup", authController.signup);
router.post("/logout", authController.logout);
router.post("/forgot-password", authController.forgotPassword);
router.get("/token", authController.token);
export default router;

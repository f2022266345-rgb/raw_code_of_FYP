import express from "express";
import chatController from "../controllers/chatController.js";
import { requireAuth } from "../middlewares/authMiddleware.js";

const router = express.Router();

// Send a message to an AI agent — returns LLM response
router.post("/", requireAuth, chatController.chatWithAgent);
router.get("/history", requireAuth, chatController.getChatHistory);

export default router;

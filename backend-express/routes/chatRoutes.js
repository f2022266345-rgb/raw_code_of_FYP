import express from "express";
import chatController from "../controllers/chatController.js";

const router = express.Router();

// requireAuth is applied at the server.js mount level — no need to repeat it here
// Send a message to an AI agent — returns LLM response
router.post("/", chatController.chatWithAgent);
router.get("/history", chatController.getChatHistory);
router.get("/memories", chatController.getChatMemories);

export default router;

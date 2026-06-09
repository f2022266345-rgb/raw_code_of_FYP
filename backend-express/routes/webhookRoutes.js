import express from "express";
import { handleClerkWebhook } from "../controllers/clerkWebhookController.js";

const router = express.Router();

// Webhook route for Clerk events
// This endpoint receives raw body for signature verification
router.post("/", handleClerkWebhook);

export default router;

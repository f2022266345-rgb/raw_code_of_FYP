import express from "express";
import { requireAuth } from "../middlewares/clerkMiddleware.js";
import authController from "../controllers/authControllers.js";
import DiagnosticProfile from "../model/DiagnosticProfile.js";

const router = express.Router();

// Clerk webhook route - for receiving Clerk events
// Note: This is handled in main server.js at /api/webhooks/clerk

// User sync - called from frontend to explicitly sync Clerk user data with database
// requireAuth already auto-syncs on every request, so this is mainly for manual calls
router.post("/sync", requireAuth, async (req, res) => {
  try {
    const { clerkId, email, fullName } = req.body;
    const authUserId = req.clerkAuth.userId;

    // Verify that the clerkId matches the authenticated user
    if (clerkId !== authUserId) {
      return res.status(403).json({ error: "User ID mismatch" });
    }

    // Call controller to sync user
    const result = await authController.syncUserWithDatabase({
      clerkId,
      email,
      fullName,
    });

    return res.status(200).json({
      success: true,
      message: "User synced successfully",
      user: result,
    });
  } catch (error) {
    console.error("User sync error:", error);
    return res.status(500).json({
      error: "Failed to sync user",
      message: error.message,
    });
  }
});

// Logout endpoint (optional, for explicit cleanup)
router.post("/logout", requireAuth, (req, res) => {
  // Clerk handles logout on the frontend
  console.log(`User ${req.clerkAuth.userId} logged out`);
  return res.status(200).json({ success: true, message: "Logged out successfully" });
});

// Check if user exists and has completed onboarding.
// requireAuth auto-creates the user in DB if they are new, so req.user is always set here.
router.get("/check", requireAuth, async (req, res) => {
  try {
    // req.user.userId is our internal PostgreSQL UUID (set by requireAuth)
    const userId = req.user.userId;

    const profile = await DiagnosticProfile.findOne({ where: { userId } });
    return res.status(200).json({
      exists: true,
      onboarded: !!profile,
    });
  } catch (error) {
    console.error("Auth check error:", error);
    return res.status(500).json({ error: "Failed to check authentication status" });
  }
});

// Get current user info
router.get("/me", requireAuth, async (req, res) => {
  try {
    // req.user is already populated by requireAuth
    return res.status(200).json({ success: true, user: req.user });
  } catch (error) {
    console.error("Get user error:", error);
    return res.status(500).json({
      error: "Failed to fetch user",
      message: error.message,
    });
  }
});

export default router;

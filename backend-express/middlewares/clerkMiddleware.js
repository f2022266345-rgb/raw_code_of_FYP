import { clerkMiddleware, getAuth, createClerkClient } from "@clerk/express";
import User from "../model/Users.js";

// Clerk backend client for fetching user details server-side
const clerkClient = createClerkClient({
  secretKey: process.env.CLERK_SECRET_KEY,
});

// Initialize Clerk middleware for automatic token verification
export const initializeClerkMiddleware = () => {
  return clerkMiddleware();
};

/**
 * Auto-upsert helper: fetches user info from Clerk and creates/updates
 * the user record in PostgreSQL. Called whenever an authenticated request
 * arrives from a user not yet in the DB.
 */
const syncClerkUserToDb = async (clerkId) => {
  try {
    const clerkUser = await clerkClient.users.getUser(clerkId);
    const email = clerkUser.emailAddresses?.[0]?.emailAddress || null;
    const fullName =
      [clerkUser.firstName, clerkUser.lastName].filter(Boolean).join(" ") ||
      clerkUser.username ||
      (email ? email.split("@")[0] : "Unknown User");

    if (!email) {
      console.warn(`Clerk user ${clerkId} has no email address.`);
      return null;
    }

    const [user] = await User.findOrCreate({
      where: { clerkId },
      defaults: { clerkId, email, fullName },
    });

    // Update in case email/name changed in Clerk
    if (user.email !== email || user.fullName !== fullName) {
      await user.update({ email, fullName });
    }

    console.log(`User auto-synced to DB: ${user.id} (${email})`);
    return user;
  } catch (err) {
    console.error("syncClerkUserToDb error:", err.message);
    return null;
  }
};

/**
 * Protect routes - requires authentication and maps Clerk ID to PostgreSQL UUID.
 * IMPORTANT: We store auth as req.clerkAuth (NOT req.auth) to avoid overwriting
 * Clerk's own req.auth function that getAuth() relies on internally.
 */
export const requireAuth = async (req, res, next) => {
  // getAuth reads Clerk's req.auth function — never overwrite req.auth
  const auth = getAuth(req);

  if (!auth.userId) {
    return res.status(401).json({
      error: "Unauthorized",
      message: "You must be authenticated to access this resource",
    });
  }

  // Store under req.clerkAuth so Clerk's req.auth function stays intact
  req.clerkAuth = auth;

  try {
    let user = await User.findOne({ where: { clerkId: auth.userId } });

    if (!user) {
      // Auto-create the user on their first authenticated request
      user = await syncClerkUserToDb(auth.userId);

      if (!user) {
        return res.status(401).json({
          error: "Unauthorized",
          message: "Could not provision user account. Please try again.",
        });
      }
    }

    // Map to req.user for backward compatibility with existing controllers
    req.user = {
      userId: user.id, // internal PostgreSQL UUID
      email: user.email,
      fullName: user.fullName,
    };

    next();
  } catch (error) {
    console.error("Clerk middleware error mapping user:", error);
    return res.status(500).json({
      error: "Internal Server Error",
      message: "Failed to map authenticated user to database profile",
    });
  }
};

// Optional authentication - populates user info if authenticated, does not block
export const optionalAuth = async (req, res, next) => {
  const auth = getAuth(req);
  req.clerkAuth = auth;

  if (auth.userId) {
    try {
      let user = await User.findOne({ where: { clerkId: auth.userId } });
      if (!user) {
        user = await syncClerkUserToDb(auth.userId);
      }
      if (user) {
        req.user = {
          userId: user.id,
          email: user.email,
          fullName: user.fullName,
        };
      }
    } catch (error) {
      console.error("Clerk optionalAuth mapping error:", error);
    }
  }
  next();
};

export default {
  initializeClerkMiddleware,
  requireAuth,
  optionalAuth,
};

import bcrypt from "bcrypt";
import jwt from "jsonwebtoken";
import db from "../model/index.js";
import {
  createSession,
  getSession,
  refreshSession,
  revokeSession,
  getIdleWindowMs,
} from "../services/sessionService.js";

const { User } = db;
const SALT_ROUNDS = 10;
// In production, keep this in your .env file!
const JWT_SECRET = process.env.JWT_SECRET || "your_super_secret_ai_academy_key";
const SESSION_IDLE_MS = getIdleWindowMs();

const issueAuthToken = ({ user, sessionId }) =>
  jwt.sign({ userId: user.userId, email: user.email, sessionId }, JWT_SECRET, {
    expiresIn: "59m",
  });

const authController = {
  // --- LOGIN: Generate JWT on Success ---
  login: async (req, res) => {
    try {
      const { email, password } = req.body;
      const user = await User.findOne({ where: { email } });

      if (!user || !(await bcrypt.compare(password, user.password))) {
        return res.status(401).json({ detail: "Invalid email or password" });
      }

      const session = createSession({ userId: user.userId, email: user.email });
      const token = issueAuthToken({ user, sessionId: session.sessionId });

      return res.status(200).json({
        token,
        session_id: session.sessionId,
        inactivity_timeout_ms: SESSION_IDLE_MS,
        expires_at: session.expiresAt,
        isAuthenticated: true,
        isOnboarded: user.isOnboarded,
        user: {
          name: user.name,
          email: user.email,
          userId: user.userId,
          isOnboarded: user.isOnboarded,
        },
      });
    } catch (error) {
      console.error("❌ Login error:", error.message);
      return res.status(500).json({ detail: "Internal Server Error" });
    }
  },

  // --- SIGNUP: Remains same ---
  signup: async (req, res) => {
    try {
      const { name, email, password } = req.body;
      const existingUser = await User.findOne({ where: { email } });
      if (existingUser)
        return res.status(400).json({ detail: "User already exists" });

      const hashedPassword = await bcrypt.hash(password, SALT_ROUNDS);
      const newUser = await User.create({
        name,
        email,
        password: hashedPassword,
      });

      return res.status(201).json({
        message: "User created successfully",
        userId: newUser.userId,
        next: "/auth?mode=login",
      });
    } catch (error) {
      return res.status(500).json({ detail: "Failed to create user" });
    }
  },

  // --- TOKEN VERIFICATION: For the Navbar check ---
  token: async (req, res) => {
    try {
      // 1. Get token from header
      const authHeader = req.headers.authorization;
      const token = authHeader && authHeader.split(" ")[1];

      if (!token) return res.status(401).json({ detail: "No token provided" });

      // 2. Verify Token
      jwt.verify(token, JWT_SECRET, async (err, decoded) => {
        if (err) return res.status(403).json({ detail: "Session expired" });

        const activeSession = getSession(decoded.sessionId);
        if (!activeSession || activeSession.userId !== decoded.userId) {
          return res.status(403).json({ detail: "Session not found" });
        }

        const refreshedSession = refreshSession(decoded.sessionId);
        if (!refreshedSession) {
          return res.status(403).json({ detail: "Session expired" });
        }

        // 3. Find user in DB to ensure they still exist
        const user = await User.findOne({ where: { userId: decoded.userId } });
        if (!user) return res.status(404).json({ detail: "User not found" });

        const refreshedToken = issueAuthToken({
          user,
          sessionId: refreshedSession.sessionId,
        });

        return res.status(200).json({
          token: refreshedToken,
          session_id: refreshedSession.sessionId,
          session_expiry: refreshedSession.expiresAt,
          inactivity_timeout_ms: SESSION_IDLE_MS,
          isAuthenticated: true,
          user: {
            userId: user.userId,
            name: user.name,
            email: user.email,
            isOnboarded: user.isOnboarded,
          },
        });
      });
    } catch (error) {
      return res.status(500).json({ detail: "Server error during validation" });
    }
  },

  logout: async (req, res) => {
    try {
      const authHeader = req.headers.authorization;
      const token = authHeader && authHeader.split(" ")[1];

      if (!token) {
        return res.status(200).json({ message: "Logged out" });
      }

      let decoded = null;
      try {
        decoded = jwt.verify(token, JWT_SECRET);
      } catch {
        return res.status(200).json({ message: "Logged out" });
      }

      if (decoded?.sessionId) {
        revokeSession(decoded.sessionId);
      }

      return res.status(200).json({ message: "Logged out" });
    } catch (error) {
      return res.status(500).json({ detail: "Failed to logout" });
    }
  },
};

export default authController;

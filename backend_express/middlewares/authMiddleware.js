import jwt from "jsonwebtoken";
import { getSession, refreshSession } from "../services/sessionService.js";

const JWT_SECRET = process.env.JWT_SECRET || "your_super_secret_ai_academy_key";

export const requireAuth = (req, res, next) => {
  const authHeader = req.headers.authorization;
  const token = authHeader && authHeader.split(" ")[1];

  if (!token) {
    return res.status(401).json({ message: "No token provided" });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    const activeSession = getSession(decoded.sessionId);

    if (!activeSession || activeSession.userId !== decoded.userId) {
      return res.status(403).json({ message: "Session expired" });
    }

    const refreshed = refreshSession(decoded.sessionId);
    if (!refreshed) {
      return res.status(403).json({ message: "Session expired" });
    }

    req.user = {
      userId: decoded.userId,
      email: decoded.email,
      sessionId: decoded.sessionId,
    };
    return next();
  } catch (error) {
    return res.status(403).json({ message: "Invalid or expired token" });
  }
};

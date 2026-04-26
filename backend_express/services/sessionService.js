import { v4 as uuid4 } from "uuid";

const SESSION_IDLE_MS = 5 * 60 * 1000;

const sessionStore = new Map();

export const createSession = ({ userId, email }) => {
  const sessionId = uuid4();
  const now = Date.now();
  const record = {
    sessionId,
    userId,
    email,
    createdAt: now,
    lastActivityAt: now,
    expiresAt: now + SESSION_IDLE_MS,
    revoked: false,
  };

  sessionStore.set(sessionId, record);
  return record;
};

export const getSession = (sessionId) => {
  if (!sessionId) return null;
  return sessionStore.get(sessionId) || null;
};

export const refreshSession = (sessionId) => {
  const existing = getSession(sessionId);
  if (!existing || existing.revoked) return null;

  const now = Date.now();
  if (existing.expiresAt <= now) {
    sessionStore.delete(sessionId);
    return null;
  }

  existing.lastActivityAt = now;
  existing.expiresAt = now + SESSION_IDLE_MS;
  sessionStore.set(sessionId, existing);
  return existing;
};

export const revokeSession = (sessionId) => {
  const existing = getSession(sessionId);
  if (!existing) return false;
  existing.revoked = true;
  sessionStore.delete(sessionId);
  return true;
};

export const revokeSessionsByUserId = (userId) => {
  for (const [sessionId, session] of sessionStore.entries()) {
    if (session.userId === userId) {
      sessionStore.delete(sessionId);
    }
  }
};

export const getIdleWindowMs = () => SESSION_IDLE_MS;

// Prevent unbounded growth in long-running dev sessions.
setInterval(() => {
  const now = Date.now();
  for (const [sessionId, session] of sessionStore.entries()) {
    if (session.revoked || session.expiresAt <= now) {
      sessionStore.delete(sessionId);
    }
  }
}, 60 * 1000);

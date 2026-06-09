import db from "../model/index.js";

const { ChatThread } = db;

export const getOrCreateActiveThread = async ({
  userId,
  routingAgent = "coordinator",
  threadId = null,
}) => {
  if (threadId) {
    const existing = await ChatThread.findOne({
      where: { id: threadId, userId },
    });
    if (existing) {
      if (existing.currentRoutingAgent !== routingAgent) {
        await existing.update({ currentRoutingAgent: routingAgent });
      }
      return existing;
    }
  }

  const latest = await ChatThread.findOne({
    where: { userId },
    order: [["createdAt", "DESC"]],
  });

  if (latest) {
    if (latest.currentRoutingAgent !== routingAgent) {
      await latest.update({ currentRoutingAgent: routingAgent });
    }
    return latest;
  }

  return ChatThread.create({
    userId,
    currentRoutingAgent: routingAgent,
  });
};

export const buildDatabaseChatHistory = async ({
  threadId,
  agentFilter = null,
  limit = 12,
}) => {
  const { ChatMessage } = db;
  const rows = await ChatMessage.findAll({
    where: { threadId },
    order: [["createdAt", "DESC"]],
    limit: Math.min(limit * 2, 48),
  });

  const filtered = agentFilter
    ? rows.filter(
        (row) =>
          row.sender === "user" ||
          row.sender === agentFilter ||
          row.sender === "coordinator",
      )
    : rows;

  return filtered
    .slice(0, limit)
    .reverse()
    .map((row) => ({
      role: row.sender === "user" ? "user" : "assistant",
      content: row.messageText,
      source: "database",
      sender: row.sender,
    }));
};

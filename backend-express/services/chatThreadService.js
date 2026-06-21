import db from "../model/index.js";

const { ChatThread } = db;

export const getOrCreateActiveThread = async ({
  userId,
  routingAgent = "coordinator",
  threadId = null,
}) => {
  // Resume a specific thread if a threadId is provided
  if (threadId) {
    const existing = await ChatThread.findOne({ where: { id: threadId, userId } });
    if (existing) return existing;
  }

  // Each agent has its own isolated thread so their conversation histories
  // don't bleed into each other. Cross-agent context is handled via the
  // agent_memory and episodic_memory tables, not via shared chat threads.
  const agentThread = await ChatThread.findOne({
    where: { userId, currentRoutingAgent: routingAgent },
    order: [["createdAt", "DESC"]],
  });

  if (agentThread) return agentThread;

  return ChatThread.create({ userId, currentRoutingAgent: routingAgent });
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

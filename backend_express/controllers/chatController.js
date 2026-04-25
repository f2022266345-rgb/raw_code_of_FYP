import db from "../model/index.js";
import { Op } from "sequelize";

const { InitialProfile, InteractionLog } = db;
const FASTAPI_BASE_URL =
  process.env.FASTAPI_BASE_URL || "http://localhost:8000";

const _buildFastApiCandidates = () => {
  const candidates = [FASTAPI_BASE_URL];
  try {
    const parsed = new URL(FASTAPI_BASE_URL);
    if (parsed.hostname === "localhost") {
      candidates.push(
        `${parsed.protocol}//127.0.0.1${parsed.port ? `:${parsed.port}` : ""}`,
      );
    } else if (parsed.hostname === "127.0.0.1") {
      candidates.push(
        `${parsed.protocol}//localhost${parsed.port ? `:${parsed.port}` : ""}`,
      );
    }
  } catch {
    // Ignore malformed env values and keep the original candidate.
  }
  return [...new Set(candidates)];
};

const _postAgentChat = async (payload) => {
  let lastError = null;
  const candidates = _buildFastApiCandidates();

  for (const baseUrl of candidates) {
    try {
      const response = await fetch(`${baseUrl}/api/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return response;
    } catch (error) {
      lastError = error;
      console.error(`FastAPI request failed via ${baseUrl}:`, error.message);
    }
  }

  throw lastError || new Error("All FastAPI endpoints failed");
};

/**
 * POST /api/chat
 * Receives a student message and agent type, fetches the student's context from DB,
 * then calls the FastAPI /api/agent/chat endpoint (State-Driven Context Injector)
 * which runs the full pipeline: DB context → state engine → Gemini → response.
 */
const chatWithAgent = async (req, res) => {
  try {
    const authenticatedUserId =
      req.user?.userId || req.user?.id || req.body?.userId || req.body?.user_id;
    const message = req.body?.message;
    const agentType = req.body?.agentType || req.body?.agent_type;
    const skillName = req.body?.skillName || req.body?.skill_name;

    if (!message || !agentType) {
      return res
        .status(400)
        .json({ message: "message and agentType are required" });
    }

    if (!authenticatedUserId) {
      return res
        .status(401)
        .json({ message: "Authenticated userId is required" });
    }

    const validAgents = [
      "academic",
      "wellness",
      "social",
      "coordinator",
      "tutor",
    ];
    if (!validAgents.includes(agentType)) {
      return res.status(400).json({
        message: `Invalid agentType. Must be one of: ${validAgents.join(", ")}`,
      });
    }

    // Fetch student name for personalized prompts
    const profile = await InitialProfile.findOne({
      where: { userId: authenticatedUserId },
    });
    const studentName = profile?.userProfile?.name || "the student";
    const resolvedSkillName = skillName || "General Studies";

    try {
      await InteractionLog.create({
        userId: authenticatedUserId,
        eventType: "chat_user",
        pagePath: "/dashboard",
        chatText: message,
        metadata: {
          agent: agentType,
          skillName: resolvedSkillName,
          source: "express_chat",
        },
      });
    } catch (logError) {
      console.error("Chat user log persistence failed:", logError);
    }

    // ── Route through FastAPI State-Driven Context Injector ─────────────────
    // The FastAPI /api/agent/chat endpoint performs:
    //   1. DB context retrieval (BKT + InitialProfile + InteractionLog + AgentMemory)
    //   2. State determination (INTELLIGENT | STRUGGLING | DEVELOPING)
    //   3. Prompt engineering (Peer-to-Peer | Socratic Tutor | Coach)
    //   4. Token-optimized Gemini call (≤150 token system instruction, no history)
    let faResponse;
    try {
      faResponse = await _postAgentChat({
        user_id: authenticatedUserId,
        skill_name: resolvedSkillName,
        message,
        agent_type: agentType,
        student_name: studentName,
      });
    } catch (fetchError) {
      console.error("FastAPI agent/chat connection error:", fetchError);
      try {
        await InteractionLog.create({
          userId: authenticatedUserId,
          eventType: "chat_assistant",
          pagePath: "/dashboard",
          chatText:
            "I'm connecting to the tutoring system. Please try again in a moment.",
          metadata: {
            agent: agentType,
            skillName: resolvedSkillName,
            source: "express_chat",
            fallback: true,
            reason: "fastapi_unreachable",
          },
        });
      } catch (logError) {
        console.error("Chat fallback log persistence failed:", logError);
      }

      return res.status(200).json({
        agent: agentType,
        response:
          "I'm connecting to the tutoring system. Please try again in a moment.",
        state: "UNKNOWN",
        persona: "Fallback",
      });
    }

    if (!faResponse.ok) {
      const errorData = await faResponse.json();
      console.error("FastAPI agent/chat error:", errorData);
      // Graceful degradation — return a helpful message instead of crashing
      try {
        await InteractionLog.create({
          userId: authenticatedUserId,
          eventType: "chat_assistant",
          pagePath: "/dashboard",
          chatText:
            "I'm connecting to the tutoring system. Could you rephrase your question?",
          metadata: {
            agent: agentType,
            skillName: resolvedSkillName,
            source: "express_chat",
            fallback: true,
          },
        });
      } catch (logError) {
        console.error("Chat fallback log persistence failed:", logError);
      }

      return res.status(200).json({
        agent: agentType,
        response:
          "I'm connecting to the tutoring system. Could you rephrase your question?",
        state: "UNKNOWN",
        persona: "Fallback",
      });
    }

    const chatData = await faResponse.json();

    try {
      await InteractionLog.create({
        userId: authenticatedUserId,
        eventType: "chat_assistant",
        pagePath: "/dashboard",
        chatText: chatData.response,
        metadata: {
          agent: agentType,
          skillName: resolvedSkillName,
          source: "express_chat",
          state: chatData.state,
          persona: chatData.persona,
        },
      });
    } catch (logError) {
      console.error("Chat assistant log persistence failed:", logError);
    }

    return res.status(200).json({
      agent: agentType,
      response: chatData.response,
      state: chatData.state,
      persona: chatData.persona,
      pMastery: chatData.p_mastery,
      bloomLevel: chatData.bloom_level,
      needsPgVector: chatData.needs_pgvector,
      systemInstructionTokens: chatData.system_instruction_tokens,
    });
  } catch (error) {
    console.error("chatWithAgent error:", error);
    return res
      .status(500)
      .json({ message: "Chat failed", error: error.message });
  }
};

const getChatHistory = async (req, res) => {
  try {
    const { userId } = req.user;
    const { agent, limit = "100" } = req.query;
    const safeLimit = Math.min(Math.max(Number(limit) || 100, 1), 200);

    const rows = await InteractionLog.findAll({
      where: {
        userId,
        eventType: { [Op.in]: ["chat_user", "chat_assistant"] },
      },
      order: [["occurredAt", "DESC"]],
      limit: safeLimit,
    });

    const filtered = agent
      ? rows.filter((row) => row.metadata?.agent === agent)
      : rows;

    const history = filtered
      .slice()
      .reverse()
      .filter((row) => row.chatText)
      .map((row) => ({
        id: row.eventId,
        role: row.eventType === "chat_user" ? "user" : "assistant",
        content: row.chatText,
        agent: row.metadata?.agent || "coordinator",
        skillName: row.metadata?.skillName || null,
        occurredAt: row.occurredAt,
      }));

    return res.status(200).json({ history });
  } catch (error) {
    console.error("getChatHistory error:", error);
    return res.status(500).json({ message: "Failed to load chat history" });
  }
};

export default { chatWithAgent, getChatHistory };

import db from "../model/index.js";
import { Op } from "sequelize";
import {
  getOrCreateActiveThread,
  buildDatabaseChatHistory,
} from "../services/chatThreadService.js";
import { mapSentimentToWellnessMarker } from "../services/profileMapper.js";
import { processNewInteractions } from "../services/cognitiveStateService.js";

const {
  DiagnosticProfile,
  AcademicProgress,
  ChatMessage,
  WellnessLog,
  InitialProfile,
} = db;

const FASTAPI_DT_URL = process.env.FASTAPI_BASE_URL || "http://localhost:8080";

async function _fetchDigitalTwinData(userId) {
  try {
    const resp = await fetch(`${FASTAPI_DT_URL}/api/digital-twin/student/${userId}`, {
      signal: AbortSignal.timeout(2000),
    });
    if (resp.ok) return await resp.json();
  } catch {
    // non-fatal
  }
  return null;
}

const FASTAPI_BASE_URL =
  process.env.FASTAPI_BASE_URL || "http://localhost:8080";

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
    // ignore malformed env
  }
  return [...new Set(candidates)];
};

const _postFastApiJson = async (path, payload) => {
  let lastError = null;
  for (const baseUrl of _buildFastApiCandidates()) {
    try {
      const response = await fetch(`${baseUrl}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`FastAPI ${path} failed (${response.status}): ${text}`);
      }
      return await response.json();
    } catch (error) {
      lastError = error;
      console.error(`FastAPI request failed via ${baseUrl}${path}:`, error.message);
    }
  }
  throw lastError || new Error("All FastAPI endpoints failed");
};

const _normalizeHistory = (history = []) => {
  if (!Array.isArray(history)) return [];
  return history
    .filter((item) => item && typeof item.content === "string")
    .map((item) => ({
      role: item.role === "assistant" ? "assistant" : "user",
      content: item.content.trim(),
      source: "frontend",
    }))
    .filter((item) => item.content.length > 0)
    .slice(-12);
};

const _mapAgentToSender = (agentType) => {
  const allowed = ["coordinator", "academic", "social", "wellness"];
  return allowed.includes(agentType) ? agentType : "coordinator";
};

const chatWithAgent = async (req, res) => {
  try {
    const userId = req.user?.userId;
    const message = req.body?.message;
    const agentType = req.body?.agentType || req.body?.agent_type || "coordinator";
    const skillName = req.body?.skillName || req.body?.skill_name || "General Studies";
    const threadId = req.body?.threadId || req.body?.thread_id || null;
    const frontendChatHistory = req.body?.chatHistory || req.body?.chat_history;

    if (!message) {
      return res.status(400).json({ message: "message is required" });
    }
    if (!userId) {
      return res.status(401).json({ message: "Authenticated userId is required" });
    }

    const validAgents = ["academic", "wellness", "social", "coordinator", "tutor"];
    if (!validAgents.includes(agentType)) {
      return res.status(400).json({
        message: `Invalid agentType. Must be one of: ${validAgents.join(", ")}`,
      });
    }

    // "tutor" is served by academic; coordinator/auto may use the LLM router.
    // All other explicit agent choices (academic, wellness, social) are ALWAYS
    // respected — we never override a user's explicit agent selection.
    const ROUTABLE_AGENTS = new Set(["coordinator", "auto", "router"]);
    let routedAgentType = _mapAgentToSender(agentType === "tutor" ? "academic" : agentType);

    if (ROUTABLE_AGENTS.has(agentType)) {
      // Only call the router when the user is in coordinator / auto mode
      try {
        const routerResp = await _postFastApiJson("/api/agent/router", {
          message,
          user_id: userId,
          skill_name: skillName,
        });
        if (routerResp?.decision?.routeTo) {
          routedAgentType = _mapAgentToSender(routerResp.decision.routeTo);
        }
      } catch (routeErr) {
        console.error("Router model call failed:", routeErr.message);
      }
    }

    const thread = await getOrCreateActiveThread({
      userId,
      routingAgent: routedAgentType,
      threadId,
    });

    const userRecord = await db.User.findByPk(userId);
    const actualStudentName = userRecord ? userRecord.fullName : (req.user?.fullName || "the student");

    const [diagnosticProfile, academicRows, initialProfile, databaseChatHistory, digitalTwinData] =
      await Promise.all([
        DiagnosticProfile.findOne({ where: { userId } }),
        AcademicProgress.findAll({ where: { userId }, limit: 8 }),
        InitialProfile.findOne({ where: { userId } }),
        buildDatabaseChatHistory({ threadId: thread.id, agentFilter: routedAgentType, limit: 16 }),
        _fetchDigitalTwinData(userRecord ? userRecord.id : userId),
      ]);

    await ChatMessage.create({
      threadId: thread.id,
      sender: "user",
      messageText: message,
      uiCardMetadata: {
        skillName,
        requestedAgent: agentType,
      },
    });

    if (routedAgentType === "wellness") {
      await WellnessLog.create({
        userId,
        sentimentMarker: mapSentimentToWellnessMarker(message),
        nearestClinicId: null,
      });
    }

    const normalizedFrontendHistory = _normalizeHistory(frontendChatHistory);
    const avgBloom =
      academicRows.length > 0
        ? Math.round(
            academicRows.reduce((sum, row) => sum + row.currentBloomLevel, 0) /
              academicRows.length,
          )
        : 1;

    const orchestrationContext = {
      profile: {
        // DiagnosticProfile fields
        priorEducation: diagnosticProfile?.priorEducation,
        primaryLanguage: diagnosticProfile?.primaryLanguage,
        englishProficiency: diagnosticProfile?.englishProficiency,
        commuteType: diagnosticProfile?.commuteType,
        techAccess: diagnosticProfile?.techAccess,
        // InitialProfile fields
        learningPreferences: initialProfile?.learningPreferences || {},
        culturalContext: initialProfile?.culturalContext || {},
        cognitiveRules: initialProfile?.cognitiveRules || {},
        activeAgents: initialProfile?.activeAgents || [],
        languageBarrierRisk: initialProfile?.languageBarrierRisk,
        wellnessSupportNeeded: initialProfile?.wellnessSupportNeeded,
        socialSupportNeeded: initialProfile?.socialSupportNeeded,
        userProfile: initialProfile?.userProfile || {},
      },
      bloomLevel: avgBloom,
      languagePreference: initialProfile?.learningPreferences?.languagePreference || "english-only",
      // Digital Twin live state
      digitalTwin: digitalTwinData
        ? {
            cognitiveState: digitalTwinData.cognitive_state?.cognitive_state,
            bloomLevel: digitalTwinData.cognitive_state?.current_bloom_level,
            frustration: digitalTwinData.cognitive_state?.frustration_estimate,
            motivation: digitalTwinData.cognitive_state?.motivation_index,
            engagement: digitalTwinData.cognitive_state?.engagement_level,
            atRisk: digitalTwinData.predictions?.at_risk_probability,
            recommendedAgent: digitalTwinData.predictions?.recommended_agent_type,
            stressLevel: digitalTwinData.wellness?.stress_level_30d,
            burnoutRisk: digitalTwinData.wellness?.burnout_risk,
          }
        : {},
      coordinatorDecision: {
        targetAgent: routedAgentType,
        matchedRule: "schema_v2_routing",
        rationale: `Routed to ${routedAgentType} based on message analysis`,
      },
    };

    let chatData;
    try {
      const payload = {
        user_id: userRecord ? userRecord.id : userId,
        thread_id: thread.id,
        skill_name: skillName,
        message,
        agent_type: routedAgentType,
        student_name: actualStudentName,
        chat_history: normalizedFrontendHistory,
        database_chat_history: databaseChatHistory,
        orchestration_context: orchestrationContext,
        stream: true
      };

      // ── Stream endpoint unavailable/disabled — use /api/agent/chat ────────
      chatData = await _postFastApiJson("/api/agent/chat", payload);
    } catch (fetchError) {
      console.error("FastAPI agent/chat connection error:", fetchError);
      const fallback =
        "I'm connecting to the tutoring system. Please try again in a moment.";

      await ChatMessage.create({
        threadId: thread.id,
        sender: routedAgentType,
        messageText: fallback,
        uiCardMetadata: { fallback: true, reason: "fastapi_unreachable" },
      });

      return res.status(200).json({
        threadId: thread.id,
        agent: routedAgentType,
        response: fallback,
        state: "UNKNOWN",
        persona: "Fallback",
      });
    }

    const uiCardMetadata = {
      skillName,
      state: chatData.state,
      persona: chatData.persona,
      pMastery: chatData.p_mastery,
      bloomLevel: chatData.bloom_level,
    };

    await ChatMessage.create({
      threadId: thread.id,
      sender: routedAgentType,
      messageText: chatData.response,
      uiCardMetadata,
    });

    if (routedAgentType === "academic" && skillName) {
      const [progress] = await AcademicProgress.findOrCreate({
        where: { userId, courseName: skillName },
        defaults: {
          userId,
          courseName: skillName,
          currentBloomLevel: chatData.bloom_level || avgBloom,
          completedTopics: [],
        },
      });
      await progress.update({ lastAssessed: new Date() });
    }

    // Connect real-time interactions to cognitive state pipeline to update frontend trends
    const interaction = await db.StudentInteraction.create({
      userId,
      eventType: "chat_message",
      contentId: skillName,
      correctness: typeof chatData.p_mastery === "number" ? chatData.p_mastery >= 0.5 : null,
      responseTimeMs: Math.floor(Math.random() * 8000) + 2000, // mock response time
      hintsRequested: message.toLowerCase().includes("hint") ? 1 : 0,
      sentimentScore: routedAgentType === "wellness" ? 0.3 : 0.8,
      sessionTimeSpentMs: 15000,
      metadata: {
        agent: routedAgentType,
        rule: "chat_inferred"
      }
    });
    
    // Recomputes BKT and sliding-window trend slopes for the dashboard
    await processNewInteractions([interaction]);

    return res.status(200).json({
      threadId: thread.id,
      agent: routedAgentType,
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
    return res.status(500).json({ message: "Chat failed", error: error.message });
  }
};

const getChatHistory = async (req, res) => {
  try {
    const { userId } = req.user;
    const {
      agent,
      role,
      q,
      date,
      fromDate,
      toDate,
      before,
      after,
      order = "desc",
      limit = "100",
      threadId,
    } = req.query;

    const safeLimit = Math.min(Math.max(Number(limit) || 100, 1), 200);
    const { ChatThread } = db;

    const threadWhere = { userId };
    if (threadId) threadWhere.id = String(threadId);

    const threads = await ChatThread.findAll({
      where: threadWhere,
      attributes: ["id"],
    });
    const threadIds = threads.map((t) => t.id);

    if (!threadIds.length) {
      return res.status(200).json({ history: [], total: 0 });
    }

    const where = { threadId: { [Op.in]: threadIds } };

    if (role === "user") where.sender = "user";
    else if (role === "assistant") {
      where.sender = { [Op.in]: ["coordinator", "academic", "social", "wellness"] };
    }

    if (agent) {
      delete where.sender;
      if (role === "user") {
        where.sender = "user";
        where.uiCardMetadata = { requestedAgent: agent };
      } else if (role === "assistant") {
        where.sender = agent;
      } else {
        where[Op.or] = [
          { sender: agent },
          { sender: "user", uiCardMetadata: { requestedAgent: agent } }
        ];
      }
    }

    if (q && String(q).trim()) {
      where.messageText = { [Op.iLike]: `%${String(q).trim()}%` };
    }

    const createdAtFilter = {};
    const applyDayRange = (start, end) => {
      createdAtFilter[Op.between] = [start, end];
    };

    if (date) {
      const d = new Date(String(date));
      if (!Number.isNaN(d.getTime())) {
        const start = new Date(d);
        start.setHours(0, 0, 0, 0);
        const end = new Date(d);
        end.setHours(23, 59, 59, 999);
        applyDayRange(start, end);
      }
    } else {
      if (fromDate) {
        const d = new Date(String(fromDate));
        if (!Number.isNaN(d.getTime())) {
          createdAtFilter[Op.gte] = new Date(d.setHours(0, 0, 0, 0));
        }
      }
      if (toDate) {
        const d = new Date(String(toDate));
        if (!Number.isNaN(d.getTime())) {
          const end = new Date(d);
          end.setHours(23, 59, 59, 999);
          createdAtFilter[Op.lte] = end;
        }
      }
    }

    if (before) {
      const beforeDate = new Date(String(before));
      if (!Number.isNaN(beforeDate.getTime())) {
        createdAtFilter[Op.lt] = beforeDate;
      }
    }
    if (after) {
      const afterDate = new Date(String(after));
      if (!Number.isNaN(afterDate.getTime())) {
        createdAtFilter[Op.gt] = afterDate;
      }
    }

    if (Object.keys(createdAtFilter).length > 0) {
      where.createdAt = createdAtFilter;
    }

    const rows = await ChatMessage.findAll({
      where,
      order: [["createdAt", String(order).toLowerCase() === "asc" ? "ASC" : "DESC"]],
      limit: safeLimit,
    });

    const history = rows
      .slice()
      .reverse()
      .map((row) => ({
        id: row.id,
        threadId: row.threadId,
        role: row.sender === "user" ? "user" : "assistant",
        content: row.messageText,
        agent: row.sender,
        uiCardMetadata: row.uiCardMetadata,
        occurredAt: row.createdAt,
      }));

    return res.status(200).json({ history, total: history.length });
  } catch (error) {
    console.error("getChatHistory error:", error);
    return res.status(500).json({ message: "Failed to load chat history" });
  }
};

const TOPIC_KEYWORDS = {
  math: ["math", "algebra", "geometry", "equation", "calculus", "statistics"],
  health: ["health", "stress", "anxiety", "wellness", "sleep", "mental"],
  family: ["family", "mother", "father", "parents", "home"],
  academics: ["exam", "study", "assignment", "course", "university", "gpa"],
  social: ["friends", "group", "social", "peer", "team", "community"],
};

const _detectTopic = (text) => {
  const lower = String(text || "").toLowerCase();
  for (const [topic, keywords] of Object.entries(TOPIC_KEYWORDS)) {
    if (keywords.some((k) => lower.includes(k))) return topic;
  }
  return "general";
};

const getChatMemories = async (req, res) => {
  try {
    const { userId } = req.user;
    const { days = "90", limit = "6" } = req.query;
    const safeDays = Math.min(Math.max(Number(days) || 90, 7), 365);
    const safeTopicLimit = Math.min(Math.max(Number(limit) || 6, 1), 12);
    const since = new Date(Date.now() - safeDays * 24 * 60 * 60 * 1000);

    const { ChatThread } = db;
    const threads = await ChatThread.findAll({
      where: { userId },
      attributes: ["id"],
    });
    const threadIds = threads.map((t) => t.id);
    if (!threadIds.length) {
      return res.status(200).json({ memories: [], generatedAt: new Date().toISOString(), days: safeDays });
    }

    const rows = await ChatMessage.findAll({
      where: {
        threadId: { [Op.in]: threadIds },
        createdAt: { [Op.gte]: since },
      },
      order: [["createdAt", "ASC"]],
      limit: 800,
    });

    const grouped = new Map();
    for (const row of rows) {
      const topic = _detectTopic(row.messageText);
      if (!grouped.has(topic)) {
        grouped.set(topic, { topic, count: 0, messages: [], firstAt: row.createdAt, lastAt: row.createdAt });
      }
      const bucket = grouped.get(topic);
      bucket.count += 1;
      bucket.lastAt = row.createdAt;
      bucket.messages.push(
        `${row.sender === "user" ? "User" : row.sender}: ${row.messageText}`,
      );
    }

    const memories = Array.from(grouped.values())
      .sort((a, b) => b.count - a.count)
      .slice(0, safeTopicLimit);

    const withSummaries = await Promise.all(
      memories.map(async (memory) => {
        const conversationText = memory.messages.slice(-30).join("\n");
        let summary = "This memory stores your recurring conversations for this topic.";
        try {
          const summaryPayload = await _postFastApiJson("/api/agent/memory/summary", {
            topic: memory.topic,
            conversation_text: conversationText,
          });
          if (summaryPayload?.summary) summary = summaryPayload.summary;
        } catch (err) {
          console.error("Memory summary generation failed:", err.message);
        }

        return {
          topic: memory.topic,
          summary,
          messageCount: memory.count,
          firstOccurredAt: memory.firstAt,
          lastOccurredAt: memory.lastAt,
        };
      }),
    );

    return res.status(200).json({
      memories: withSummaries,
      generatedAt: new Date().toISOString(),
      days: safeDays,
    });
  } catch (error) {
    console.error("getChatMemories error:", error);
    return res.status(500).json({ message: "Failed to generate chat memories" });
  }
};

export default { chatWithAgent, getChatHistory, getChatMemories };

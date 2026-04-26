import db from "../model/index.js";
import { Op } from "sequelize";
import { processNewInteractions } from "../services/cognitiveStateService.js";

const { InitialProfile, InteractionLog, StudentProfileState } = db;
const FASTAPI_BASE_URL =
  process.env.FASTAPI_BASE_URL || "http://localhost:8080";

const { StudentInteraction } = db;

const CHAT_POSITIVE_WORDS = [
  "good",
  "great",
  "happy",
  "confident",
  "excellent",
  "better",
  "amazing",
  "success",
  "calm",
];

const CHAT_NEGATIVE_WORDS = [
  "bad",
  "sad",
  "stressed",
  "anxious",
  "worried",
  "confused",
  "angry",
  "hard",
  "difficult",
  "failed",
];

const estimateSentiment = (text = "") => {
  const cleaned = String(text).toLowerCase().trim();
  if (!cleaned) return { score: null, label: null };

  const words = cleaned.split(/\s+/).filter(Boolean);
  if (!words.length) return { score: null, label: null };

  let positive = 0;
  let negative = 0;

  for (const word of words) {
    if (CHAT_POSITIVE_WORDS.includes(word)) positive += 1;
    if (CHAT_NEGATIVE_WORDS.includes(word)) negative += 1;
  }

  const score = (positive - negative) / words.length;
  if (score > 0.15) return { score, label: "positive" };
  if (score < -0.15) return { score, label: "negative" };
  return { score, label: "neutral" };
};

const logStudentInteraction = async ({
  userId,
  sessionId,
  eventType,
  messageText,
  agentType,
  contentId,
  metadata,
}) => {
  const sentiment = estimateSentiment(messageText || "");

  const created = await StudentInteraction.create({
    userId,
    sessionId: sessionId || null,
    eventType,
    contentId: contentId || null,
    agentType: agentType || null,
    messageText: messageText || null,
    sentimentScore: sentiment.score,
    sentimentLabel: sentiment.label,
    metadata: metadata || null,
    occurredAt: new Date(),
  });

  await processNewInteractions([created]);
};

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

const _postFastApiJson = async (path, payload) => {
  let lastError = null;
  const candidates = _buildFastApiCandidates();

  for (const baseUrl of candidates) {
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
      console.error(
        `FastAPI request failed via ${baseUrl}${path}:`,
        error.message,
      );
    }
  }

  throw lastError || new Error("All FastAPI endpoints failed");
};

const _postAgentChat = async (payload) =>
  _postFastApiJson("/api/agent/chat", payload);

const _coordinatorDecisionRules = ({ profile, profileState }) => {
  const stressLevel = Number(profile?.userProfile?.stressLevel ?? 0);
  const confidence = Number(profile?.userProfile?.academicConfidence ?? 50);
  const frustration = Number(profileState?.frustrationEstimate ?? 0.35);
  const readiness = Number(profileState?.readinessEstimate ?? 0.4);
  const mastery = Number(profileState?.masterySummary?.avgMastery ?? 0.4);

  if (frustration >= 0.65 || stressLevel >= 7) {
    return {
      targetAgent: "wellness",
      rationale: "High frustration or stress detected.",
      matchedRule: "if frustration/stress high -> wellness",
    };
  }

  if (confidence <= 40 || readiness <= 0.35) {
    return {
      targetAgent: "social",
      rationale: "Low confidence/readiness suggests social support routing.",
      matchedRule: "if confidence low -> social",
    };
  }

  if (mastery >= 0.75 || readiness >= 0.65) {
    return {
      targetAgent: "academic",
      rationale: "Mastery/readiness indicates level-up academic challenge.",
      matchedRule: "if mastery ready -> academic level up",
    };
  }

  return {
    targetAgent: "coordinator",
    rationale: "No high-priority escalation rule matched.",
    matchedRule: "default coordinator",
  };
};

const _normalizeHistory = (history = [], source = "frontend") => {
  if (!Array.isArray(history)) return [];

  return history
    .filter((item) => item && typeof item.content === "string")
    .map((item) => ({
      role: item.role === "assistant" ? "assistant" : "user",
      content: item.content.trim(),
      source,
    }))
    .filter((item) => item.content.length > 0);
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
    const frontendChatHistory = req.body?.chatHistory || req.body?.chat_history;

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
    const profileState = await StudentProfileState.findOne({
      where: { userId: authenticatedUserId },
    });

    const coordinatorDecision =
      agentType === "coordinator"
        ? _coordinatorDecisionRules({ profile, profileState })
        : {
            targetAgent: agentType,
            rationale: "Direct agent request from caller.",
            matchedRule: "direct agent",
          };

    const routedAgentType = coordinatorDecision.targetAgent;

    const studentName = profile?.userProfile?.name || "the student";
    const resolvedSkillName = skillName || "General Studies";

    const recentDbRows = await InteractionLog.findAll({
      where: {
        userId: authenticatedUserId,
        eventType: { [Op.in]: ["chat_user", "chat_assistant"] },
      },
      order: [["occurredAt", "DESC"]],
      limit: 24,
    });

    const databaseChatHistory = recentDbRows
      .slice()
      .reverse()
      .filter(
        (row) =>
          row.chatText &&
          (!row.metadata?.agent || row.metadata?.agent === routedAgentType),
      )
      .map((row) => ({
        role: row.eventType === "chat_assistant" ? "assistant" : "user",
        content: row.chatText,
        source: "database",
      }))
      .slice(-12);

    const normalizedFrontendHistory = _normalizeHistory(
      frontendChatHistory,
      "frontend",
    ).slice(-12);

    try {
      await InteractionLog.create({
        userId: authenticatedUserId,
        sessionId: req.user?.sessionId || null,
        eventType: "chat_user",
        pagePath: "/dashboard",
        chatText: message,
        metadata: {
          agent: agentType,
          routedAgent: routedAgentType,
          skillName: resolvedSkillName,
          source: "express_chat",
          coordinatorDecision,
        },
      });
      await logStudentInteraction({
        userId: authenticatedUserId,
        sessionId: req.user?.sessionId,
        eventType: "chat_message_user",
        messageText: message,
        agentType,
        contentId: resolvedSkillName,
        metadata: {
          source: "express_chat",
          routedAgent: routedAgentType,
          coordinatorDecision,
        },
      });
    } catch (logError) {
      console.error("Chat user log persistence failed:", logError);
    }

    const orchestrationContext = {
      profile: {
        educationalBackground: profile?.educationalBackground || {},
        learningPreferences: profile?.learningPreferences || {},
        culturalContext: profile?.culturalContext || {},
        cognitiveRules: profile?.cognitiveRules || {},
      },
      hiddenState: profileState
        ? {
            masterySummary: profileState.masterySummary || {},
            frustrationEstimate: profileState.frustrationEstimate,
            engagementEstimate: profileState.engagementEstimate,
            readinessEstimate: profileState.readinessEstimate,
            trendSlopes: {
              accuracy: profileState.accuracyTrendSlope,
              time: profileState.timeTrendSlope,
              hints: profileState.hintTrendSlope,
            },
          }
        : {},
      bloomLevel: profile?.bloomLevel ?? 1,
      languagePreference:
        profile?.learningPreferences?.languagePreference || "english-only",
      coordinatorDecision,
    };

    try {
      await logStudentInteraction({
        userId: authenticatedUserId,
        sessionId: req.user?.sessionId,
        eventType: "coordinator_routing_decision",
        messageText: JSON.stringify(coordinatorDecision),
        agentType: "coordinator",
        contentId: resolvedSkillName,
        metadata: {
          source: "express_chat_orchestration",
          routedAgent: routedAgentType,
          coordinatorDecision,
        },
      });
    } catch (logError) {
      console.error("Coordinator routing persistence failed:", logError);
    }

    // ── Route through FastAPI State-Driven Context Injector ─────────────────
    // The FastAPI /api/agent/chat endpoint performs:
    //   1. DB context retrieval (BKT + InitialProfile + InteractionLog + AgentMemory)
    //   2. State determination (INTELLIGENT | STRUGGLING | DEVELOPING)
    //   3. Prompt engineering (Peer-to-Peer | Socratic Tutor | Coach)
    //   4. Token-optimized Gemini call (≤150 token system instruction, no history)
    let faResponse;
    try {
      const chatData = await _postAgentChat({
        user_id: authenticatedUserId,
        skill_name: resolvedSkillName,
        message,
        agent_type: routedAgentType,
        student_name: studentName,
        chat_history: normalizedFrontendHistory,
        database_chat_history: databaseChatHistory,
        orchestration_context: orchestrationContext,
      });

      try {
        await InteractionLog.create({
          userId: authenticatedUserId,
          sessionId: req.user?.sessionId || null,
          eventType: "chat_assistant",
          pagePath: "/dashboard",
          chatText: chatData.response,
          metadata: {
            agent: agentType,
            routedAgent: routedAgentType,
            skillName: resolvedSkillName,
            source: "express_chat",
            state: chatData.state,
            persona: chatData.persona,
            coordinatorDecision,
          },
        });
        await logStudentInteraction({
          userId: authenticatedUserId,
          sessionId: req.user?.sessionId,
          eventType: "chat_message_agent",
          messageText: chatData.response,
          agentType,
          contentId: resolvedSkillName,
          metadata: {
            source: "express_chat",
            routedAgent: routedAgentType,
            state: chatData.state,
            persona: chatData.persona,
            coordinatorDecision,
          },
        });
      } catch (logError) {
        console.error("Chat assistant log persistence failed:", logError);
      }

      return res.status(200).json({
        agent: routedAgentType,
        coordinatorDecision,
        response: chatData.response,
        state: chatData.state,
        persona: chatData.persona,
        pMastery: chatData.p_mastery,
        bloomLevel: chatData.bloom_level,
        needsPgVector: chatData.needs_pgvector,
        systemInstructionTokens: chatData.system_instruction_tokens,
      });
    } catch (fetchError) {
      console.error("FastAPI agent/chat connection error:", fetchError);
      try {
        await InteractionLog.create({
          userId: authenticatedUserId,
          sessionId: req.user?.sessionId || null,
          eventType: "chat_assistant",
          pagePath: "/dashboard",
          chatText:
            "I'm connecting to the tutoring system. Please try again in a moment.",
          metadata: {
            agent: agentType,
            routedAgent: routedAgentType,
            skillName: resolvedSkillName,
            source: "express_chat",
            fallback: true,
            reason: "fastapi_unreachable",
            coordinatorDecision,
          },
        });
        await logStudentInteraction({
          userId: authenticatedUserId,
          sessionId: req.user?.sessionId,
          eventType: "chat_message_agent",
          messageText:
            "I'm connecting to the tutoring system. Please try again in a moment.",
          agentType,
          contentId: resolvedSkillName,
          metadata: {
            source: "express_chat",
            routedAgent: routedAgentType,
            fallback: true,
            reason: "fastapi_unreachable",
            coordinatorDecision,
          },
        });
      } catch (logError) {
        console.error("Chat fallback log persistence failed:", logError);
      }

      return res.status(200).json({
        agent: routedAgentType,
        coordinatorDecision,
        response:
          "I'm connecting to the tutoring system. Please try again in a moment.",
        state: "UNKNOWN",
        persona: "Fallback",
      });
    }
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
    const {
      agent,
      role,
      q,
      date,
      fromDate,
      toDate,
      order = "desc",
      limit = "100",
    } = req.query;
    const safeLimit = Math.min(Math.max(Number(limit) || 100, 1), 200);

    const where = {
      userId,
      eventType: { [Op.in]: ["chat_user", "chat_assistant"] },
    };

    if (role === "user") {
      where.eventType = "chat_user";
    } else if (role === "assistant") {
      where.eventType = "chat_assistant";
    }

    if (q && String(q).trim()) {
      where.chatText = { [Op.iLike]: `%${String(q).trim()}%` };
    }

    let rangeStart = null;
    let rangeEnd = null;
    if (date) {
      const d = new Date(String(date));
      if (!Number.isNaN(d.getTime())) {
        rangeStart = new Date(d);
        rangeStart.setHours(0, 0, 0, 0);
        rangeEnd = new Date(d);
        rangeEnd.setHours(23, 59, 59, 999);
      }
    } else {
      if (fromDate) {
        const d = new Date(String(fromDate));
        if (!Number.isNaN(d.getTime())) {
          rangeStart = new Date(d);
          rangeStart.setHours(0, 0, 0, 0);
        }
      }
      if (toDate) {
        const d = new Date(String(toDate));
        if (!Number.isNaN(d.getTime())) {
          rangeEnd = new Date(d);
          rangeEnd.setHours(23, 59, 59, 999);
        }
      }
    }

    if (rangeStart && rangeEnd) {
      where.occurredAt = { [Op.between]: [rangeStart, rangeEnd] };
    } else if (rangeStart) {
      where.occurredAt = { [Op.gte]: rangeStart };
    } else if (rangeEnd) {
      where.occurredAt = { [Op.lte]: rangeEnd };
    }

    const rows = await InteractionLog.findAll({
      where,
      order: [
        ["occurredAt", String(order).toLowerCase() === "asc" ? "ASC" : "DESC"],
      ],
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

    return res.status(200).json({ history, total: history.length });
  } catch (error) {
    console.error("getChatHistory error:", error);
    return res.status(500).json({ message: "Failed to load chat history" });
  }
};

const TOPIC_KEYWORDS = {
  math: ["math", "algebra", "geometry", "equation", "calculus", "statistics"],
  health: [
    "health",
    "stress",
    "anxiety",
    "wellness",
    "sleep",
    "mental",
    "diet",
  ],
  family: [
    "family",
    "mother",
    "father",
    "parents",
    "sister",
    "brother",
    "home",
  ],
  academics: [
    "exam",
    "study",
    "assignment",
    "course",
    "university",
    "gpa",
    "skill",
  ],
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
    const rows = await InteractionLog.findAll({
      where: {
        userId,
        eventType: { [Op.in]: ["chat_user", "chat_assistant"] },
        occurredAt: { [Op.gte]: since },
      },
      order: [["occurredAt", "ASC"]],
      limit: 800,
    });

    const grouped = new Map();
    for (const row of rows) {
      if (!row.chatText) continue;
      const topic = _detectTopic(row.chatText);
      if (!grouped.has(topic)) {
        grouped.set(topic, {
          topic,
          count: 0,
          messages: [],
          firstAt: row.occurredAt,
          lastAt: row.occurredAt,
        });
      }

      const bucket = grouped.get(topic);
      bucket.count += 1;
      bucket.lastAt = row.occurredAt;
      bucket.messages.push(
        `${row.eventType === "chat_assistant" ? "Assistant" : "User"}: ${row.chatText}`,
      );
    }

    const memories = Array.from(grouped.values())
      .sort((a, b) => b.count - a.count)
      .slice(0, safeTopicLimit);

    const withSummaries = await Promise.all(
      memories.map(async (memory) => {
        const conversationText = memory.messages.slice(-30).join("\n");
        let summary =
          "This memory stores your recurring conversations for this topic.";
        try {
          const summaryPayload = await _postFastApiJson(
            "/api/agent/memory/summary",
            {
              topic: memory.topic,
              conversation_text: conversationText,
            },
          );
          if (summaryPayload?.summary) {
            summary = summaryPayload.summary;
          }
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
    return res
      .status(500)
      .json({ message: "Failed to generate chat memories" });
  }
};

export default { chatWithAgent, getChatHistory, getChatMemories };

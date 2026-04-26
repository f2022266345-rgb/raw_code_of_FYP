import db from "../model/index.js";
import { processNewInteractions } from "../services/cognitiveStateService.js";

const { InteractionLog, StudentInteraction } = db;

const POSITIVE_WORDS = [
  "good",
  "great",
  "happy",
  "confident",
  "excellent",
  "better",
  "nice",
  "amazing",
  "calm",
  "focused",
  "success",
];

const NEGATIVE_WORDS = [
  "bad",
  "sad",
  "stressed",
  "anxious",
  "worried",
  "confused",
  "angry",
  "upset",
  "hard",
  "difficult",
  "failed",
];

const toNumberOrNull = (value) => {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const toIntegerOrNull = (value) => {
  const parsed = toNumberOrNull(value);
  return parsed === null ? null : Math.round(parsed);
};

const estimateSentiment = (text = "") => {
  const cleaned = String(text).toLowerCase().trim();
  if (!cleaned) {
    return { score: null, label: null };
  }

  const words = cleaned.split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return { score: null, label: null };
  }

  let positive = 0;
  let negative = 0;

  for (const word of words) {
    if (POSITIVE_WORDS.includes(word)) {
      positive += 1;
    }
    if (NEGATIVE_WORDS.includes(word)) {
      negative += 1;
    }
  }

  const score = (positive - negative) / words.length;

  if (score > 0.15) {
    return { score, label: "positive" };
  }
  if (score < -0.15) {
    return { score, label: "negative" };
  }
  return { score, label: "neutral" };
};

const normalizeEvent = (payload, userId) => {
  const chatText = payload?.chatText
    ? String(payload.chatText).slice(0, 2000)
    : null;
  const fallbackSentiment = estimateSentiment(chatText || "");
  const sentimentScore =
    toNumberOrNull(payload?.sentimentScore) ?? fallbackSentiment.score;

  return {
    userId,
    sessionId: payload?.sessionId || null,
    eventType: payload?.eventType || "unknown",
    pagePath: payload?.pagePath || null,
    correct: typeof payload?.correct === "boolean" ? payload.correct : null,
    responseTimeMs: toIntegerOrNull(payload?.responseTimeMs),
    hintsUsed: toIntegerOrNull(payload?.hintsUsed),
    attempts: toIntegerOrNull(payload?.attempts),
    timeOnPageMs: toIntegerOrNull(payload?.timeOnPageMs),
    clickCount: toIntegerOrNull(payload?.clickCount),
    mood: payload?.mood ? String(payload.mood).slice(0, 100) : null,
    confidenceScore: toNumberOrNull(payload?.confidenceScore),
    chatText,
    sentimentScore,
    sentimentLabel:
      payload?.sentimentLabel ||
      (sentimentScore === null ? null : fallbackSentiment.label),
    metadata: payload?.metadata || null,
    occurredAt: payload?.occurredAt ? new Date(payload.occurredAt) : new Date(),
  };
};

const toStudentInteraction = (event) => {
  const metadata = event?.metadata || {};
  const hintsRequested = Number.isFinite(Number(event?.hintsUsed))
    ? Number(event.hintsUsed)
    : null;

  return {
    userId: event.userId,
    sessionId: event.sessionId || metadata?.sessionId || null,
    eventType: event.eventType || "unknown",
    contentId: metadata?.contentId || metadata?.skillName || null,
    agentType: metadata?.agent || metadata?.agentType || null,
    correctness: typeof event.correct === "boolean" ? event.correct : null,
    hintsRequested,
    attempts: Number.isFinite(Number(event.attempts))
      ? Number(event.attempts)
      : null,
    responseTimeMs: Number.isFinite(Number(event.responseTimeMs))
      ? Number(event.responseTimeMs)
      : null,
    sessionTimeSpentMs: Number.isFinite(Number(event.timeOnPageMs))
      ? Number(event.timeOnPageMs)
      : null,
    messageText: event.chatText || null,
    sentimentScore: Number.isFinite(Number(event.sentimentScore))
      ? Number(event.sentimentScore)
      : null,
    sentimentLabel: event.sentimentLabel || null,
    metadata,
    occurredAt: event.occurredAt || new Date(),
  };
};

const persistStudentInteractions = async (events = []) => {
  if (!events.length) return;

  const mapped = events.map(toStudentInteraction);
  await StudentInteraction.bulkCreate(mapped);

  // Explicitly log hint_requested when hints are used in any event.
  const hintRows = [];
  for (const row of mapped) {
    if (
      Number.isFinite(Number(row.hintsRequested)) &&
      Number(row.hintsRequested) > 0
    ) {
      hintRows.push({
        ...row,
        eventType: "hint_requested",
      });
    }
  }

  if (hintRows.length > 0) {
    await StudentInteraction.bulkCreate(hintRows);
  }

  await processNewInteractions(mapped);
};

const logObservation = async (req, res) => {
  try {
    const { userId } = req.user;
    const normalized = normalizeEvent(req.body, userId);

    const created = await InteractionLog.create(normalized);
    await persistStudentInteractions([normalized]);

    return res.status(201).json({
      message: "Observation logged",
      eventId: created.eventId,
    });
  } catch (error) {
    console.error("Observation log error:", error);
    return res.status(500).json({ message: "Failed to log observation" });
  }
};

const logObservationBatch = async (req, res) => {
  try {
    const { userId } = req.user;
    const events = Array.isArray(req.body?.events) ? req.body.events : [];

    if (events.length === 0) {
      return res.status(400).json({ message: "events array is required" });
    }

    const limitedEvents = events.slice(0, 200);
    const normalized = limitedEvents.map((event) =>
      normalizeEvent(event, userId),
    );

    await InteractionLog.bulkCreate(normalized);
    await persistStudentInteractions(normalized);

    return res.status(201).json({
      message: "Observation batch logged",
      count: normalized.length,
    });
  } catch (error) {
    console.error("Observation batch log error:", error);
    return res.status(500).json({ message: "Failed to log observation batch" });
  }
};

const logHintRequested = async (req, res) => {
  try {
    const { userId, sessionId } = req.user;
    const {
      contentId = null,
      agentType = null,
      pagePath = null,
      metadata = {},
    } = req.body || {};

    const payload = {
      userId,
      sessionId: req.body?.sessionId || sessionId || null,
      eventType: "hint_requested",
      pagePath,
      hintsUsed: 1,
      attempts: Number.isFinite(Number(req.body?.attempts))
        ? Number(req.body.attempts)
        : null,
      responseTimeMs: Number.isFinite(Number(req.body?.responseTimeMs))
        ? Number(req.body.responseTimeMs)
        : null,
      metadata: {
        ...metadata,
        contentId,
        agent: agentType,
      },
      occurredAt: new Date(),
    };

    const logRow = await InteractionLog.create(payload);
    await persistStudentInteractions([payload]);

    return res.status(201).json({
      message: "Hint request logged",
      eventId: logRow.eventId,
    });
  } catch (error) {
    console.error("Hint log error:", error);
    return res.status(500).json({ message: "Failed to log hint request" });
  }
};

const getObservationSummary = async (req, res) => {
  try {
    const { userId } = req.user;

    const logs = await InteractionLog.findAll({
      where: { userId },
      order: [["occurredAt", "DESC"]],
      limit: 500,
    });

    const totalEvents = logs.length;
    const correctnessEvents = logs.filter(
      (log) => typeof log.correct === "boolean",
    );
    const correctCount = correctnessEvents.filter(
      (log) => log.correct === true,
    ).length;

    const responseEvents = logs.filter((log) =>
      Number.isFinite(Number(log.responseTimeMs)),
    );
    const totalResponseTime = responseEvents.reduce(
      (sum, log) => sum + Number(log.responseTimeMs || 0),
      0,
    );

    const hintEvents = logs.filter((log) =>
      Number.isFinite(Number(log.hintsUsed)),
    );
    const totalHints = hintEvents.reduce(
      (sum, log) => sum + Number(log.hintsUsed || 0),
      0,
    );

    const attemptsEvents = logs.filter((log) =>
      Number.isFinite(Number(log.attempts)),
    );
    const totalAttempts = attemptsEvents.reduce(
      (sum, log) => sum + Number(log.attempts || 0),
      0,
    );

    const engagementTimeEvents = logs.filter((log) =>
      Number.isFinite(Number(log.timeOnPageMs)),
    );
    const totalTimeOnPageMs = engagementTimeEvents.reduce(
      (sum, log) => sum + Number(log.timeOnPageMs || 0),
      0,
    );

    const engagementClickEvents = logs.filter((log) =>
      Number.isFinite(Number(log.clickCount)),
    );
    const totalClicks = engagementClickEvents.reduce(
      (sum, log) => sum + Number(log.clickCount || 0),
      0,
    );

    const moodLatest = logs.find((log) => log.mood)?.mood || null;
    const confidenceLatest = logs.find((log) =>
      Number.isFinite(Number(log.confidenceScore)),
    )?.confidenceScore;

    const sentimentEvents = logs.filter((log) =>
      Number.isFinite(Number(log.sentimentScore)),
    );
    const avgSentimentScore = sentimentEvents.length
      ? sentimentEvents.reduce(
          (sum, log) => sum + Number(log.sentimentScore || 0),
          0,
        ) / sentimentEvents.length
      : null;

    return res.status(200).json({
      totalEvents,
      learning: {
        accuracy: correctnessEvents.length
          ? Number((correctCount / correctnessEvents.length).toFixed(3))
          : null,
        averageResponseTimeMs: responseEvents.length
          ? Math.round(totalResponseTime / responseEvents.length)
          : null,
        totalHintsUsed: totalHints,
        totalAttempts,
      },
      engagement: {
        totalTimeOnPageMs,
        totalClicks,
      },
      selfReports: {
        mood: moodLatest,
        confidenceScore:
          confidenceLatest !== undefined ? Number(confidenceLatest) : null,
      },
      sentiment: {
        averageScore:
          avgSentimentScore !== null
            ? Number(avgSentimentScore.toFixed(3))
            : null,
      },
    });
  } catch (error) {
    console.error("Observation summary error:", error);
    return res
      .status(500)
      .json({ message: "Failed to load observation summary" });
  }
};

export default {
  logObservation,
  logObservationBatch,
  logHintRequested,
  getObservationSummary,
};

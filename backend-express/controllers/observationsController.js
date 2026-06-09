import db from "../model/index.js";
import { mapSentimentToWellnessMarker } from "../services/profileMapper.js";

const { WellnessLog, AcademicProgress, SocialMetrics } = db;

const logObservation = async (req, res) => {
  try {
    const { userId } = req.user;
    const { eventType } = req.body || {};
    await persistObservation(userId, req.body || {});

    return res.status(201).json({
      message: "Observation logged",
      eventType: eventType || "unknown",
    });
  } catch (error) {
    console.error("Observation log error:", error);
    return res.status(500).json({ message: "Failed to log observation" });
  }
};

const persistObservation = async (userId, payload = {}) => {
  const { eventType, mood, chatText, metadata = {} } = payload;

  if (eventType === "self_report" || mood || chatText) {
    await WellnessLog.create({
      userId,
      sentimentMarker: mood || mapSentimentToWellnessMarker(chatText || ""),
      nearestClinicId: metadata?.nearestClinicId || null,
    });
  }

  if (eventType === "learning_attempt" && metadata?.courseName) {
    const row = await AcademicProgress.findOne({
      where: { userId, courseName: metadata.courseName },
    });
    if (row) {
      await row.update({ lastAssessed: new Date() });
    }
  }

  if (eventType === "social_profile_update") {
    const social = await SocialMetrics.findOne({ where: { userId } });
    if (social) {
      await social.update({
        linkedinOptimized: metadata.linkedinOptimized ?? social.linkedinOptimized,
        instagramOptimized: metadata.instagramOptimized ?? social.instagramOptimized,
        communicationScore:
          metadata.communicationScore ?? social.communicationScore,
        lastUpdated: new Date(),
      });
    }
  }
};

const logObservationBatch = async (req, res) => {
  try {
    const { userId } = req.user;
    const events = Array.isArray(req.body?.events) ? req.body.events : [];
    if (!events.length) {
      return res.status(400).json({ message: "events array is required" });
    }

    const limited = events.slice(0, 200);
    for (const event of limited) {
      await persistObservation(userId, event);
    }

    return res.status(201).json({
      message: "Observation batch logged",
      count: limited.length,
    });
  } catch (error) {
    console.error("Observation batch log error:", error);
    return res.status(500).json({ message: "Failed to log observation batch" });
  }
};

const logHintRequested = async (req, res) => {
  return logObservation(
    {
      user: req.user,
      body: {
        eventType: "hint_requested",
        metadata: req.body || {},
      },
    },
    res,
  );
};

const getObservationSummary = async (req, res) => {
  try {
    const { userId } = req.user;
    const logs = await WellnessLog.findAll({
      where: { userId },
      order: [["loggedAt", "DESC"]],
      limit: 100,
    });

    const academicRows = await AcademicProgress.findAll({ where: { userId } });
    const social = await SocialMetrics.findOne({ where: { userId } });

    return res.status(200).json({
      totalEvents: logs.length,
      wellness: {
        latestSentiment: logs[0]?.sentimentMarker || null,
        markers: logs.map((l) => l.sentimentMarker),
      },
      academic: {
        coursesTracked: academicRows.length,
        averageBloom:
          academicRows.length > 0
            ? Number(
                (
                  academicRows.reduce((s, r) => s + r.currentBloomLevel, 0) /
                  academicRows.length
                ).toFixed(2),
              )
            : null,
      },
      social: social
        ? {
            linkedinOptimized: social.linkedinOptimized,
            instagramOptimized: social.instagramOptimized,
            communicationScore: social.communicationScore,
          }
        : null,
    });
  } catch (error) {
    console.error("Observation summary error:", error);
    return res.status(500).json({ message: "Failed to load observation summary" });
  }
};

export default {
  logObservation,
  logObservationBatch,
  logHintRequested,
  getObservationSummary,
};

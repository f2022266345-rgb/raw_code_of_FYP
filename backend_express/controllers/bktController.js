import db from "../model/index.js";
import { Op } from "sequelize";

const { BktSkillMastery, InteractionLog, InitialProfile } = db;
const FASTAPI_BASE_URL =
  process.env.FASTAPI_BASE_URL || "http://localhost:8000";

/**
 * BKT Update Formula:
 * After evidence (correct/incorrect), update mastery probability.
 *
 * P(L | correct) = P(L) * (1 - slip) / [P(L) * (1 - slip) + (1 - P(L)) * guess]
 * P(L | incorrect) = P(L) * slip / [P(L) * slip + (1 - P(L)) * (1 - guess)]
 * P(L_new) = P(L | evidence) + (1 - P(L | evidence)) * p_transit
 */
const applyBktUpdate = (pMastery, pSlip, pGuess, pTransit, isCorrect) => {
  const slip = pSlip ?? 0.1;
  const guess = pGuess ?? 0.15;
  const transit = pTransit ?? 0.1;

  let pLGivenEvidence;
  if (isCorrect) {
    const numerator = pMastery * (1 - slip);
    const denominator = numerator + (1 - pMastery) * guess;
    pLGivenEvidence = denominator > 0 ? numerator / denominator : pMastery;
  } else {
    const numerator = pMastery * slip;
    const denominator = numerator + (1 - pMastery) * (1 - guess);
    pLGivenEvidence = denominator > 0 ? numerator / denominator : pMastery;
  }

  // Apply learning (transition)
  const pNew = pLGivenEvidence + (1 - pLGivenEvidence) * transit;
  return Math.min(Math.max(parseFloat(pNew.toFixed(4)), 0), 1);
};

/**
 * GET /api/bkt/skills
 * Returns all BKT skill rows for the authenticated user, sorted by mastery ascending
 * so the student can see what needs attention first.
 */
const getUserSkills = async (req, res) => {
  try {
    const { userId } = req.user;

    const skills = await BktSkillMastery.findAll({
      where: { userId },
      order: [["p_mastery", "ASC"]],
      attributes: [
        "skillName",
        "category",
        "pMastery",
        "pInit",
        "pTransit",
        "pGuess",
        "pSlip",
        "pForget",
        "practiceCount",
        "lastPracticedAt",
      ],
    });

    if (skills.length === 0) {
      return res.status(200).json({
        message: "No BKT skills found. Complete onboarding to initialize.",
        skills: [],
        summary: {
          totalSkills: 0,
          avgMastery: 0,
          masteredCount: 0,
          needsAttentionCount: 0,
        },
      });
    }

    const masteryValues = skills.map((s) => s.pMastery);
    const avgMastery =
      masteryValues.reduce((a, b) => a + b, 0) / masteryValues.length;
    const masteredCount = skills.filter((s) => s.pMastery >= 0.8).length;
    const needsAttentionCount = skills.filter((s) => s.pMastery < 0.5).length;

    return res.status(200).json({
      skills: skills.map((s) => ({
        name: s.skillName,
        category: s.category,
        mastery: Math.round(s.pMastery * 100), // [0–100] for UI
        pMastery: s.pMastery,
        pInit: s.pInit,
        pTransit: s.pTransit,
        pGuess: s.pGuess,
        pSlip: s.pSlip,
        pForget: s.pForget,
        practiceCount: s.practiceCount,
        lastPracticedAt: s.lastPracticedAt,
        trend:
          s.practiceCount === 0 ? "stable" : s.pMastery >= 0.7 ? "up" : "down",
      })),
      summary: {
        totalSkills: skills.length,
        avgMastery: parseFloat((avgMastery * 100).toFixed(1)),
        masteredCount,
        needsAttentionCount,
      },
    });
  } catch (error) {
    console.error("getUserSkills error:", error);
    return res.status(500).json({ message: "Failed to retrieve BKT skills" });
  }
};

/**
 * POST /api/bkt/skills/:skillName/update
 * Updates the BKT mastery for a skill after a learning interaction.
 * Body: { correct: boolean }
 */
const updateSkillMastery = async (req, res) => {
  try {
    const { userId } = req.user;
    const skillName = decodeURIComponent(req.params.skillName);
    const { correct } = req.body;

    if (typeof correct !== "boolean") {
      return res
        .status(400)
        .json({ message: "correct (boolean) is required in request body" });
    }

    const skill = await BktSkillMastery.findOne({
      where: { userId, skillName },
    });
    if (!skill) {
      return res
        .status(404)
        .json({ message: `Skill '${skillName}' not found for this user` });
    }

    const prevMastery = skill.pMastery;
    const newMastery = applyBktUpdate(
      skill.pMastery,
      skill.pSlip,
      skill.pGuess,
      skill.pTransit,
      correct,
    );

    await skill.update({
      pMastery: newMastery,
      practiceCount: skill.practiceCount + 1,
      lastPracticedAt: new Date(),
    });

    return res.status(200).json({
      skillName,
      prevMastery: parseFloat((prevMastery * 100).toFixed(1)),
      newMastery: parseFloat((newMastery * 100).toFixed(1)),
      correct,
      masteryChange: parseFloat(((newMastery - prevMastery) * 100).toFixed(2)),
    });
  } catch (error) {
    console.error("updateSkillMastery error:", error);
    return res.status(500).json({ message: "Failed to update skill mastery" });
  }
};

/**
 * GET /api/bkt/state
 * Fetches the last 7 interaction logs for the user, derives frustration/accuracy/boredom
 * windows, then calls FastAPI /api/analyze-state to get the cognitive state label.
 */
const analyzeState = async (req, res) => {
  try {
    const { userId } = req.user;

    // Get the last 7 interaction logs
    const logs = await InteractionLog.findAll({
      where: { userId },
      order: [["occurred_at", "DESC"]],
      limit: 7,
      attributes: [
        "correct",
        "responseTimeMs",
        "hintsUsed",
        "sentimentScore",
        "timeOnPageMs",
      ],
    });

    if (logs.length < 3) {
      return res.status(200).json({
        state: "NEUTRAL",
        reason: "Insufficient interaction data (need at least 3 events)",
      });
    }

    // Reverse to oldest → newest for slope calculation
    const orderedLogs = [...logs].reverse();

    // Derive frustration from sentiment + hints + response time
    const recentFrustration = orderedLogs.map((log) => {
      const sentiment =
        typeof log.sentimentScore === "number" ? log.sentimentScore : 0;
      const hintFactor = Math.min((log.hintsUsed ?? 0) * 0.1, 0.3);
      // Negative sentiment → higher frustration; many hints → more frustrated
      const frustration = Math.max(
        0,
        Math.min(1, 0.5 - sentiment + hintFactor),
      );
      return parseFloat(frustration.toFixed(3));
    });

    // Accuracy from correct field
    const recentAccuracy = orderedLogs.map((log) => {
      if (typeof log.correct === "boolean") return log.correct ? 1 : 0;
      return 0.5; // Unknown → neutral
    });

    // Boredom from slow response time + high time on page (lingering without engagement)
    const avgResponseMs =
      orderedLogs
        .filter((l) => l.responseTimeMs)
        .reduce((a, b) => a + (b.responseTimeMs || 0), 0) /
      (orderedLogs.length || 1);

    const recentBoredom = orderedLogs.map((log) => {
      const timeOnPage = log.timeOnPageMs ?? 0;
      const responseMs = log.responseTimeMs ?? avgResponseMs;
      // High time on page relative to response time suggests boredom
      const boredom = Math.min(
        1,
        timeOnPage > 120000 && responseMs > 10000 ? 0.7 : 0.2,
      );
      return boredom;
    });

    // Call FastAPI trend engine
    const faResponse = await fetch(`${FASTAPI_BASE_URL}/api/analyze-state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recent_frustration: recentFrustration,
        recent_accuracy: recentAccuracy,
        recent_boredom: recentBoredom,
      }),
    });

    if (!faResponse.ok) {
      return res
        .status(200)
        .json({ state: "NEUTRAL", reason: "Trend engine unavailable" });
    }

    const stateData = await faResponse.json();
    return res.status(200).json({
      state: stateData.state,
      signals: stateData.signals,
      eventsAnalyzed: orderedLogs.length,
    });
  } catch (error) {
    console.error("analyzeState error:", error);
    return res
      .status(500)
      .json({ message: "Failed to analyze cognitive state" });
  }
};

export default { getUserSkills, updateSkillMastery, analyzeState };

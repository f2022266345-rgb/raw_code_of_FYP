import { Op } from "sequelize";
import db from "../model/index.js";

const { BktSkillMastery, StudentInteraction, StudentProfileState } = db;

const WINDOW_MIN = 5;
const WINDOW_MAX = 10;
const WINDOW_DEFAULT = 8;

const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));

const toPlain = (row) =>
  typeof row?.toJSON === "function" ? row.toJSON() : row;

const safeNumber = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

const average = (values = []) => {
  if (!values.length) return null;
  const total = values.reduce((sum, v) => sum + v, 0);
  return total / values.length;
};

const linearRegressionSlope = (values = []) => {
  if (!Array.isArray(values) || values.length < 2) return 0;

  const n = values.length;
  const xMean = (n - 1) / 2;
  const yMean = average(values) ?? 0;

  let numerator = 0;
  let denominator = 0;

  for (let i = 0; i < n; i += 1) {
    const dx = i - xMean;
    const dy = values[i] - yMean;
    numerator += dx * dy;
    denominator += dx * dx;
  }

  if (denominator === 0) return 0;
  return numerator / denominator;
};

const trendLabel = (slope, epsilon = 0.02) => {
  if (slope > epsilon) return "rising";
  if (slope < -epsilon) return "declining";
  return "stable";
};

const resolveSkillName = (interaction) => {
  const plain = toPlain(interaction) || {};
  const metadata = plain.metadata || {};
  return (
    plain.contentId ||
    metadata.skillName ||
    metadata.contentId ||
    metadata.skill_id ||
    null
  );
};

const applyBktUpdate = (
  pMastery,
  pSlip,
  pGuess,
  pTransit,
  pForget,
  isCorrect,
) => {
  const slip = pSlip ?? 0.1;
  const guess = pGuess ?? 0.15;
  const transit = pTransit ?? 0.1;
  const forget = pForget ?? 0;

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

  const afterLearning = pLGivenEvidence + (1 - pLGivenEvidence) * transit;
  const afterForgetting = afterLearning * (1 - forget);
  return clamp(parseFloat(afterForgetting.toFixed(4)), 0, 1);
};

const findSkillRow = async (userId, skillName) => {
  if (!skillName) return null;

  const exact = await BktSkillMastery.findOne({ where: { userId, skillName } });
  if (exact) return exact;

  return BktSkillMastery.findOne({
    where: {
      userId,
      skillName: { [Op.iLike]: `%${String(skillName).trim()}%` },
    },
    order: [["practiceCount", "DESC"]],
  });
};

export const updateBktFromInteraction = async (interaction) => {
  const row = toPlain(interaction) || {};
  const correctness =
    typeof row.correctness === "boolean" ? row.correctness : null;
  if (correctness === null) return null;

  const skillName = resolveSkillName(row);
  if (!skillName || !row.userId) return null;

  const skill = await findSkillRow(row.userId, skillName);
  if (!skill) return null;

  const newMastery = applyBktUpdate(
    skill.pMastery,
    skill.pSlip,
    skill.pGuess,
    skill.pTransit,
    skill.pForget,
    correctness,
  );

  await skill.update({
    pMastery: newMastery,
    practiceCount: Number(skill.practiceCount || 0) + 1,
    lastPracticedAt: new Date(),
  });

  return {
    skillName: skill.skillName,
    prevMastery: skill.pMastery,
    newMastery,
    correct: correctness,
  };
};

const buildMasterySummary = async (userId) => {
  const rows = await BktSkillMastery.findAll({
    where: { userId },
    attributes: ["skillName", "category", "pMastery", "practiceCount"],
  });

  if (!rows.length) {
    return {
      totalSkills: 0,
      avgMastery: 0,
      masteredCount: 0,
      weakSkills: [],
    };
  }

  const avgMastery =
    rows.reduce((sum, row) => sum + Number(row.pMastery || 0), 0) / rows.length;
  const masteredCount = rows.filter(
    (row) => Number(row.pMastery || 0) >= 0.8,
  ).length;
  const weakSkills = [...rows]
    .sort((a, b) => Number(a.pMastery || 0) - Number(b.pMastery || 0))
    .slice(0, 5)
    .map((row) => ({
      skill: row.skillName,
      category: row.category,
      pKnow: Number(Number(row.pMastery || 0).toFixed(4)),
    }));

  return {
    totalSkills: rows.length,
    avgMastery: Number(avgMastery.toFixed(4)),
    masteredCount,
    weakSkills,
  };
};

const normalizeWindowSize = (windowSize) => {
  const size = Number(windowSize || WINDOW_DEFAULT);
  if (!Number.isFinite(size)) return WINDOW_DEFAULT;
  return Math.min(WINDOW_MAX, Math.max(WINDOW_MIN, Math.round(size)));
};

export const recomputeAndStoreProfileState = async (userId, options = {}) => {
  const windowSize = normalizeWindowSize(options.windowSize);

  const recentRows = await StudentInteraction.findAll({
    where: { userId },
    order: [["occurredAt", "DESC"]],
    limit: windowSize,
  });

  const windowRows = recentRows.map(toPlain).reverse();
  const masterySummary = await buildMasterySummary(userId);

  const accuracyValues = windowRows
    .filter((row) => typeof row.correctness === "boolean")
    .map((row) => (row.correctness ? 1 : 0));

  const responseTimeValues = windowRows
    .map((row) => safeNumber(row.responseTimeMs))
    .filter((v) => v !== null);

  const hintValues = windowRows
    .map((row) => safeNumber(row.hintsRequested))
    .filter((v) => v !== null);

  const sentimentValues = windowRows
    .map((row) => safeNumber(row.sentimentScore))
    .filter((v) => v !== null);

  const sessionTimeValues = windowRows
    .map((row) => safeNumber(row.sessionTimeSpentMs))
    .filter((v) => v !== null);

  const accuracyTrendSlope = Number(
    linearRegressionSlope(accuracyValues).toFixed(6),
  );
  const timeTrendSlope = Number(
    linearRegressionSlope(responseTimeValues).toFixed(6),
  );
  const hintTrendSlope = Number(linearRegressionSlope(hintValues).toFixed(6));

  const avgAccuracy = average(accuracyValues) ?? 0.5;
  const avgResponseMs = average(responseTimeValues) ?? 12000;
  const avgHints = average(hintValues) ?? 0;
  const avgSentiment = average(sentimentValues) ?? 0;
  const avgSessionMs = average(sessionTimeValues) ?? 0;

  const timeNorm = clamp(avgResponseMs / 30000, 0, 1);
  const hintsNorm = clamp(avgHints / 3, 0, 1);
  const negativeSentimentNorm = clamp((1 - avgSentiment) / 2, 0, 1);
  const sessionNorm = clamp(avgSessionMs / 180000, 0, 1);
  const activityDensity = clamp(windowRows.length / windowSize, 0, 1);

  const frustrationEstimate = Number(
    clamp(
      0.4 * (1 - avgAccuracy) +
        0.25 * hintsNorm +
        0.2 * timeNorm +
        0.15 * negativeSentimentNorm,
      0,
      1,
    ).toFixed(4),
  );

  const engagementEstimate = Number(
    clamp(
      0.45 * activityDensity + 0.35 * sessionNorm + 0.2 * (1 - hintsNorm),
      0,
      1,
    ).toFixed(4),
  );

  const readinessEstimate = Number(
    clamp(
      0.45 * masterySummary.avgMastery +
        0.25 * avgAccuracy +
        0.2 * engagementEstimate +
        0.1 * (1 - frustrationEstimate),
      0,
      1,
    ).toFixed(4),
  );

  const hiddenState = {
    latentStates: {
      mastery: {
        pKnowAvg: masterySummary.avgMastery,
        label:
          masterySummary.avgMastery >= 0.8
            ? "high"
            : masterySummary.avgMastery >= 0.5
              ? "moderate"
              : "low",
      },
      frustration: {
        value: frustrationEstimate,
        label:
          frustrationEstimate >= 0.67
            ? "high"
            : frustrationEstimate >= 0.34
              ? "moderate"
              : "low",
      },
      readiness: {
        value: readinessEstimate,
        label:
          readinessEstimate >= 0.67
            ? "ready"
            : readinessEstimate >= 0.34
              ? "developing"
              : "not_ready",
      },
      engagement: {
        value: engagementEstimate,
        label:
          engagementEstimate >= 0.67
            ? "high"
            : engagementEstimate >= 0.34
              ? "moderate"
              : "low",
      },
    },
    trendSignals: {
      accuracy: {
        slope: accuracyTrendSlope,
        direction: trendLabel(accuracyTrendSlope, 0.03),
      },
      responseTime: {
        slope: timeTrendSlope,
        direction: trendLabel(timeTrendSlope, 250),
      },
      hints: {
        slope: hintTrendSlope,
        direction: trendLabel(hintTrendSlope, 0.15),
      },
    },
    observableToLatentMapping: {
      observables: {
        avgAccuracy: Number(avgAccuracy.toFixed(4)),
        avgResponseMs: Number(avgResponseMs.toFixed(2)),
        avgHints: Number(avgHints.toFixed(3)),
        avgSentiment: Number(avgSentiment.toFixed(4)),
        avgSessionMs: Number(avgSessionMs.toFixed(2)),
      },
      notes: [
        "Higher hints/time and lower accuracy increase frustration.",
        "Higher average mastery and positive accuracy trend increase readiness.",
        "Engagement combines interaction density, session time, and persistence.",
      ],
    },
  };

  const [stateRow] = await StudentProfileState.findOrCreate({
    where: { userId },
    defaults: {
      userId,
    },
  });

  await stateRow.update({
    masterySummary,
    accuracyTrendSlope,
    timeTrendSlope,
    hintTrendSlope,
    frustrationEstimate,
    engagementEstimate,
    readinessEstimate,
    hiddenState,
    interactionWindow: windowSize,
    lastComputedAt: new Date(),
  });

  return toPlain(stateRow);
};

export const processNewInteractions = async (interactions = []) => {
  if (!Array.isArray(interactions) || interactions.length === 0) return;

  const rows = interactions.map(toPlain).filter(Boolean);
  const users = new Set();

  for (const row of rows) {
    if (!row.userId) continue;
    users.add(row.userId);
    await updateBktFromInteraction(row);
  }

  for (const userId of users) {
    await recomputeAndStoreProfileState(userId);
  }
};

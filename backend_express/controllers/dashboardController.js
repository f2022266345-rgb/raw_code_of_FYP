import db from "../model/index.js";

const { User, InitialProfile, InteractionLog } = db;

const toAgentResults = (profileRecord) => {
  const prediction = profileRecord?.aiPrediction || {};
  const profile = profileRecord?.userProfile || {};

  const probabilityRaw = Number(prediction.success_probability || 0);
  const probability = Number.isFinite(probabilityRaw)
    ? Math.round(probabilityRaw * 100)
    : 0;

  return {
    academic: `Prediction: ${prediction.status || "Unknown"} (${probability}%)`,
    social: `Social battery: ${profile.socialBattery || "moderate"}`,
    wellness: `Stress level: ${profile.stressLevel ?? "N/A"}`,
  };
};

const getMyDashboard = async (req, res) => {
  try {
    const { userId } = req.user;

    const user = await User.findOne({ where: { userId } });
    if (!user) {
      return res.status(404).json({ message: "User not found" });
    }

    const onboardingProfile = await InitialProfile.findOne({
      where: { userId },
    });

    const recentLogs = await InteractionLog.findAll({
      where: { userId },
      order: [["occurredAt", "DESC"]],
      limit: 200,
    });

    const totalTimeOnPageMs = recentLogs.reduce(
      (sum, log) => sum + Number(log.timeOnPageMs || 0),
      0,
    );
    const totalClicks = recentLogs.reduce(
      (sum, log) => sum + Number(log.clickCount || 0),
      0,
    );
    const averageResponseTimeMs = (() => {
      const withResponse = recentLogs.filter((log) =>
        Number.isFinite(Number(log.responseTimeMs)),
      );
      if (!withResponse.length) {
        return null;
      }
      const total = withResponse.reduce(
        (sum, log) => sum + Number(log.responseTimeMs || 0),
        0,
      );
      return Math.round(total / withResponse.length);
    })();

    const latestMood = recentLogs.find((log) => log.mood)?.mood || null;
    const latestConfidence =
      recentLogs.find((log) => Number.isFinite(Number(log.confidenceScore)))
        ?.confidenceScore ?? null;

    return res.status(200).json({
      user: {
        userId: user.userId,
        name: user.name,
        email: user.email,
        isOnboarded: user.isOnboarded,
      },
      onboardingCompleted: Boolean(onboardingProfile),
      studentProfile: onboardingProfile
        ? {
            educationalBackground: onboardingProfile.educationalBackground,
            learningPreferences: onboardingProfile.learningPreferences,
            culturalContext: onboardingProfile.culturalContext,
            diagnosticAssessment: onboardingProfile.diagnosticAssessment || {},
          }
        : null,
      aiPrediction: onboardingProfile
        ? {
            user_profile: onboardingProfile.userProfile,
            ai_prediction: onboardingProfile.aiPrediction,
          }
        : null,
      agentsStatus: {
        isAnalyzing: false,
        academic: onboardingProfile ? "complete" : "idle",
        social: onboardingProfile ? "complete" : "idle",
        wellness: onboardingProfile ? "complete" : "idle",
      },
      agentResults: onboardingProfile
        ? toAgentResults(onboardingProfile)
        : {
            academic: null,
            social: null,
            wellness: null,
          },
      observations: {
        totalEvents: recentLogs.length,
        totalTimeOnPageMs,
        totalClicks,
        averageResponseTimeMs,
        latestMood,
        latestConfidence,
      },
    });
  } catch (error) {
    console.error("Dashboard fetch error:", error);
    return res.status(500).json({ message: "Failed to load dashboard" });
  }
};

export default {
  getMyDashboard,
};

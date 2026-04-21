import db from "../model/index.js";

const { User, InitialProfile, InteractionLog, BktSkillMastery } = db;

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

    const onboardingProfile = await InitialProfile.findOne({ where: { userId } });

    const recentLogs = await InteractionLog.findAll({
      where: { userId },
      order: [["occurredAt", "DESC"]],
      limit: 200,
    });

    // ── Observation aggregations ─────────────────────────────────────────────
    const totalTimeOnPageMs = recentLogs.reduce(
      (sum, log) => sum + Number(log.timeOnPageMs || 0), 0,
    );
    const totalClicks = recentLogs.reduce(
      (sum, log) => sum + Number(log.clickCount || 0), 0,
    );
    const withResponse = recentLogs.filter((log) =>
      Number.isFinite(Number(log.responseTimeMs)),
    );
    const averageResponseTimeMs = withResponse.length
      ? Math.round(withResponse.reduce((s, l) => s + Number(l.responseTimeMs || 0), 0) / withResponse.length)
      : null;

    const latestMood = recentLogs.find((log) => log.mood)?.mood || null;
    const latestConfidence = recentLogs.find((log) =>
      Number.isFinite(Number(log.confidenceScore)),
    )?.confidenceScore ?? null;

    // ── BKT Summary ──────────────────────────────────────────────────────────
    let bktSummary = null;
    if (onboardingProfile) {
      const bktSkills = await BktSkillMastery.findAll({
        where: { userId },
        attributes: ["skillName", "category", "pMastery", "practiceCount"],
      });

      if (bktSkills.length > 0) {
        const avgMastery =
          bktSkills.reduce((s, sk) => s + sk.pMastery, 0) / bktSkills.length;
        const masteredCount = bktSkills.filter((sk) => sk.pMastery >= 0.8).length;
        const needsAttentionCount = bktSkills.filter((sk) => sk.pMastery < 0.5).length;
        const practicedCount = bktSkills.filter((sk) => sk.practiceCount > 0).length;

        // Weakest skills (for dashboard "focus areas")
        const weakestSkills = bktSkills
          .sort((a, b) => a.pMastery - b.pMastery)
          .slice(0, 5)
          .map((sk) => ({ name: sk.skillName, category: sk.category, mastery: Math.round(sk.pMastery * 100) }));

        bktSummary = {
          totalSkills: bktSkills.length,
          avgMastery: parseFloat((avgMastery * 100).toFixed(1)),
          masteredCount,
          needsAttentionCount,
          practicedCount,
          weakestSkills,
        };
      }
    }

    // ── Agent status ─────────────────────────────────────────────────────────
    const activeAgents = onboardingProfile?.activeAgents ?? [];
    const agentsStatus = {
      isAnalyzing: false,
      academic: onboardingProfile ? "complete" : "idle",
      social: activeAgents.includes("social") ? "complete" : "idle",
      wellness: activeAgents.includes("wellness") ? "complete" : "idle",
    };

    return res.status(200).json({
      user: {
        userId: user.userId,
        name: user.name,
        email: user.email,
        isOnboarded: user.isOnboarded,
        persistentLearnerId: user.persistentLearnerId,
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
            bloomLevel: onboardingProfile.bloomLevel,
            languageBarrierRisk: onboardingProfile.languageBarrierRisk,
            activeAgents: onboardingProfile.activeAgents,
          }
        : null,
      agentsStatus,
      agentResults: onboardingProfile
        ? toAgentResults(onboardingProfile)
        : { academic: null, social: null, wellness: null },
      bktSummary,
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

export default { getMyDashboard };

import db from "../model/index.js";

const { User, InitialProfile, BktSkillMastery } = db;
const FASTAPI_BASE_URL =
  process.env.FASTAPI_BASE_URL || "http://localhost:8080";

const computeCognitiveRules = ({
  languageBarrierRisk,
  learningBarriersScore,
  bloomLevelPredicted,
  learningPreferences,
}) => {
  const pace =
    learningBarriersScore >= 0.7 || bloomLevelPredicted <= 2
      ? "slow"
      : learningBarriersScore >= 0.45
        ? "moderate"
        : "adaptive-fast";

  const chunking =
    learningBarriersScore >= 0.6 || bloomLevelPredicted <= 2
      ? "micro-chunks"
      : bloomLevelPredicted <= 4
        ? "medium-chunks"
        : "concept-blocks";

  const preferredLanguage =
    learningPreferences?.languagePreference || "english-only";
  const languageSupport =
    languageBarrierRisk >= 0.6 || preferredLanguage !== "english-only"
      ? "bilingual-scaffold"
      : "english-primary";

  return {
    pacing: pace,
    chunking,
    languageSupport,
  };
};

const activateAgentMappings = ({
  academicSupportNeeded,
  socialSupportNeeded,
  wellnessSupportNeeded,
  predictedAgents,
}) => {
  const agents = new Set(["coordinator"]);

  if (academicSupportNeeded) {
    agents.add("academic");
  }
  if (socialSupportNeeded) {
    agents.add("social");
  }
  if (wellnessSupportNeeded) {
    agents.add("wellness");
  }

  if (Array.isArray(predictedAgents)) {
    predictedAgents.forEach((agent) => {
      if (["coordinator", "academic", "social", "wellness"].includes(agent)) {
        agents.add(agent);
      }
    });
  }

  if (!agents.has("academic")) {
    agents.add("academic");
  }

  return Array.from(agents);
};

const onboardingController = async (req, res) => {
  console.log("Received onboarding data:", req.body);
  const { userId } = req.user || {};

  const {
    educationalBackground,
    learningPreferences,
    culturalContext,
    diagnosticAssessment,
  } = req.body || {};

  // Validate required fields
  if (!educationalBackground || !learningPreferences || !culturalContext) {
    return res.status(400).json({
      message:
        "educationalBackground, learningPreferences, and culturalContext are required",
    });
  }

  if (!userId) {
    return res.status(401).json({ message: "Unauthorized request" });
  }

  try {
    const user = await User.findOne({ where: { userId } });
    if (!user) {
      return res.status(404).json({ message: "User not found" });
    }

    // ── Step 1: Save raw onboarding profile immediately ───────────────────────
    let profileRecord = await InitialProfile.findOne({ where: { userId } });
    if (!profileRecord) {
      profileRecord = await InitialProfile.create({
        userId,
        educationalBackground,
        learningPreferences,
        culturalContext,
        diagnosticAssessment: diagnosticAssessment || {},
        userProfile: {},
        aiPrediction: {},
        bloomLevelPredicted: 1,
        bloomLevel: 1,
        languageBarrierRisk: 0.2,
        learningBarriersScore: 0.0,
        wellnessSupportNeeded: false,
        socialSupportNeeded: false,
        academicSupportNeeded: true,
        cognitiveRules: {},
        activeAgents: ["coordinator", "academic"],
      });
    } else {
      await profileRecord.update({
        educationalBackground,
        learningPreferences,
        culturalContext,
        diagnosticAssessment: diagnosticAssessment || {},
      });
    }

    // ── Step 2: Call FastAPI for ML predictions ───────────────────────────────
    const fastApiResponse = await fetch(
      `${FASTAPI_BASE_URL}/api/predict/initial-profile`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          educationalBackground,
          learningPreferences,
          culturalContext,
          diagnosticAssessment: diagnosticAssessment || null,
        }),
      },
    );

    if (!fastApiResponse.ok) {
      const errorData = await fastApiResponse.json();
      console.error("FastAPI prediction error:", errorData);
      return res.status(fastApiResponse.status).json({
        message: "Failed to generate prediction from FastAPI",
        error: errorData,
      });
    }

    const predictionData = await fastApiResponse.json();
    console.log("\n\n\n\n\nFastAPI prediction result:", predictionData);

    const prediction = predictionData?.prediction || {};
    const userProfile = prediction.user_profile || {};
    const aiPrediction = prediction.ai_prediction || {};
    const bloomLevelPredicted =
      prediction.bloom_level_predicted ?? prediction.bloom_level ?? 1;
    const bloomLevel = bloomLevelPredicted;
    const languageBarrierRisk = prediction.language_barrier_risk ?? 0.2;
    const learningBarriersScore = prediction.learning_barriers_score ?? 0.0;
    const wellnessSupportNeeded = prediction.wellness_support_needed ?? false;
    const socialSupportNeeded = prediction.social_support_needed ?? false;
    const academicSupportNeeded = prediction.academic_support_needed ?? true;
    const cognitiveRules = computeCognitiveRules({
      languageBarrierRisk,
      learningBarriersScore,
      bloomLevelPredicted,
      learningPreferences,
    });
    const activeAgents = activateAgentMappings({
      academicSupportNeeded,
      socialSupportNeeded,
      wellnessSupportNeeded,
      predictedAgents: prediction.active_agents,
    });
    const persistentLearnerId = predictionData.persistentLearnerId;

    // ── Step 3: Save prediction outputs + cognitive rules + agents ───────────
    await profileRecord.update({
      persistentLearnerId,
      userProfile,
      aiPrediction,
      bloomLevelPredicted,
      bloomLevel,
      languageBarrierRisk,
      learningBarriersScore,
      wellnessSupportNeeded,
      socialSupportNeeded,
      academicSupportNeeded,
      cognitiveRules,
      activeAgents,
    });

    // ── Step 4: Save persistentLearnerId to User record ───────────────────────
    user.isOnboarded = true;
    user.persistentLearnerId = persistentLearnerId;
    await user.save();

    // ── Step 5: Seed BKT skill mastery rows for this user ─────────────────────
    // Fetch the full skill list from FastAPI (190 skills with BKT params)
    try {
      const skillsResponse = await fetch(`${FASTAPI_BASE_URL}/api/bkt/skills`);
      if (skillsResponse.ok) {
        const skillsData = await skillsResponse.json();
        const skills = skillsData.skills || [];

        // Check if BKT rows already exist for this user
        const existingCount = await BktSkillMastery.count({
          where: { userId },
        });

        if (existingCount === 0 && skills.length > 0) {
          // Bulk insert all skills — initial mastery = p_init from CSV
          const rows = skills.map((skill) => ({
            userId,
            skillName: skill.skillName,
            category: skill.category,
            pMastery: skill.pInit ?? 0.3,
            pInit: skill.pInit,
            pTransit: skill.pTransit,
            pGuess: skill.pGuess,
            pSlip: skill.pSlip,
            pForget: skill.pForget,
            practiceCount: 0,
          }));

          // Insert in batches of 50 to avoid query size limits
          const BATCH_SIZE = 50;
          for (let i = 0; i < rows.length; i += BATCH_SIZE) {
            await BktSkillMastery.bulkCreate(rows.slice(i, i + BATCH_SIZE), {
              ignoreDuplicates: true,
            });
          }
          console.log(`✅ Seeded ${rows.length} BKT skills for user ${userId}`);
        } else {
          console.log(
            `BKT skills already seeded for user ${userId} (${existingCount} rows)`,
          );
        }
      }
    } catch (bktError) {
      // BKT seeding failure is non-fatal — log and continue
      console.error(
        "⚠️ BKT skill seeding failed (non-fatal):",
        bktError.message,
      );
    }

    // ── Step 6: Return dashboard-ready onboarding response ────────────────────
    return res.status(200).json({
      userId,
      persistentLearnerId,
      studentProfile: {
        educationalBackground,
        learningPreferences,
        culturalContext,
        diagnosticAssessment: diagnosticAssessment || {},
      },
      aiPrediction: {
        ...prediction,
        bloom_level_predicted: bloomLevelPredicted,
        language_barrier_risk: languageBarrierRisk,
        learning_barriers_score: learningBarriersScore,
        wellness_support_needed: wellnessSupportNeeded,
        social_support_needed: socialSupportNeeded,
        academic_support_needed: academicSupportNeeded,
      },
      cognitiveRules,
      bloomLevel,
      bloomLevelPredicted,
      languageBarrierRisk,
      learningBarriersScore,
      wellnessSupportNeeded,
      socialSupportNeeded,
      academicSupportNeeded,
      activeAgents,
      pipeline: [
        "form_received",
        "raw_profile_saved",
        "prediction_completed",
        "prediction_saved",
        "cognitive_rules_created",
        "agents_activated",
        "dashboard_ready",
      ],
    });
  } catch (error) {
    console.error("Error in onboarding controller:", error);
    return res.status(500).json({
      message: "Failed to process onboarding request",
      error: error.message,
    });
  }
};

export default onboardingController;

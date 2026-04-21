import db from "../model/index.js";

const { User, InitialProfile, BktSkillMastery } = db;

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

    // ── Step 1: Call FastAPI for ML predictions ───────────────────────────────
    const fastApiResponse = await fetch(
      "http://localhost:8000/api/predict/initial-profile",
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
    console.log("FastAPI prediction result:", predictionData);

    const prediction = predictionData?.prediction || {};
    const userProfile = prediction.user_profile || {};
    const aiPrediction = prediction.ai_prediction || {};
    const bloomLevel = prediction.bloom_level ?? 1;
    const languageBarrierRisk = prediction.language_barrier_risk ?? 0.2;
    const activeAgents = prediction.active_agents ?? ["academic", "coordinator"];
    const persistentLearnerId = predictionData.persistentLearnerId;

    // ── Step 2: Save onboarding profile to DB ─────────────────────────────────
    await InitialProfile.upsert({
      userId,
      persistentLearnerId,
      educationalBackground,
      learningPreferences,
      culturalContext,
      diagnosticAssessment: diagnosticAssessment || {},
      userProfile,
      aiPrediction,
      bloomLevel,
      languageBarrierRisk,
      activeAgents,
    });

    // ── Step 3: Save persistentLearnerId to User record ───────────────────────
    user.isOnboarded = true;
    user.persistentLearnerId = persistentLearnerId;
    await user.save();

    // ── Step 4: Seed BKT skill mastery rows for this user ─────────────────────
    // Fetch the full skill list from FastAPI (190 skills with BKT params)
    try {
      const skillsResponse = await fetch("http://localhost:8000/api/bkt/skills");
      if (skillsResponse.ok) {
        const skillsData = await skillsResponse.json();
        const skills = skillsData.skills || [];

        // Check if BKT rows already exist for this user
        const existingCount = await BktSkillMastery.count({ where: { userId } });

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
          console.log(`BKT skills already seeded for user ${userId} (${existingCount} rows)`);
        }
      }
    } catch (bktError) {
      // BKT seeding failure is non-fatal — log and continue
      console.error("⚠️ BKT skill seeding failed (non-fatal):", bktError.message);
    }

    // ── Step 5: Return consolidated response ──────────────────────────────────
    return res.status(200).json({
      userId,
      persistentLearnerId,
      studentProfile: {
        educationalBackground,
        learningPreferences,
        culturalContext,
        diagnosticAssessment: diagnosticAssessment || {},
      },
      aiPrediction: prediction,
      bloomLevel,
      languageBarrierRisk,
      activeAgents,
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

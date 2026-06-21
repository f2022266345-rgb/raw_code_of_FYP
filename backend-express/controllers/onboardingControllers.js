// controllers/onboardingControllers.js
// Handles the initial profiling pipeline:
// 1. Save raw form data to initial_profiles (JSONB)
// 2. Save structured profile to diagnostic_profiles
// 3. Seed academic_progress rows
// 4. Seed social_metrics with cultural context
// 5. Create initial wellness_logs entry
// 6. Call FastAPI ML for bloom/language/support predictions
// 7. Update initial_profiles with ML outputs

import db from "../model/index.js";
import InitialProfile from "../model/InitialProfile.js";
import {
  mapToDiagnosticProfile,
  mapToSocialMetrics,
  mapToInitialWellness,
  deriveCognitiveRules,
  deriveActiveAgents,
} from "../services/profileMapper.js";

const {
  User,
  DiagnosticProfile,
  AcademicProgress,
  SocialMetrics,
  WellnessLog,
} = db;

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || "http://localhost:8080";

const onboardingController = async (req, res) => {
  const userId = req.user?.userId;

  if (!userId) {
    return res.status(401).json({ message: "Unauthorized request" });
  }

  const {
    educationalBackground = {},
    learningPreferences = {},
    culturalContext = {},
    diagnosticAssessment = {},
  } = req.body || {};

  if (!educationalBackground || !learningPreferences || !culturalContext) {
    return res.status(400).json({
      message: "educationalBackground, learningPreferences, and culturalContext are required",
    });
  }

  try {
    // ── Verify user exists ─────────────────────────────────────────
    const user = await User.findOne({ where: { id: userId } });
    if (!user) {
      return res.status(404).json({ message: "User not found" });
    }

    // ── Step 1: Map form data to structured fields ─────────────────
    const mapped = mapToDiagnosticProfile({
      educationalBackground,
      learningPreferences,
      culturalContext,
      diagnosticAssessment,
    });

    const socialData = mapToSocialMetrics({ culturalContext });
    const wellnessData = mapToInitialWellness({ culturalContext });
    const cognitiveRules = deriveCognitiveRules({
      educationalBackground,
      learningPreferences,
      culturalContext,
    });

    // ── Step 2: Upsert InitialProfile (raw JSONB store) ───────────
    let initialProfile = await InitialProfile.findOne({ where: { userId } });
    const rawPayload = {
      userId,
      educationalBackground,
      learningPreferences,
      culturalContext,
      diagnosticAssessment: diagnosticAssessment || null,
      userProfile: {
        // Institution
        university: educationalBackground.university,
        program: educationalBackground.program,
        major: educationalBackground.program,       // alias used by dashboard store
        // Location & language
        city: culturalContext.city,
        background: culturalContext.background,
        primaryLanguage: culturalContext.primaryLanguage,
        englishProficiency: educationalBackground.englishProficiency,
        // Learning
        studyPace: learningPreferences.studyPace,
        languagePreference: learningPreferences.languagePreference,
        learningStyles: learningPreferences.learningStyles,
        studyHoursPerWeek: learningPreferences.studyHoursPerWeek,
        strongestSubject: learningPreferences.strongestSubject,
        weakestSubject: learningPreferences.weakestSubject,
        // Self-assessment (Step 4)
        currentSemester: diagnosticAssessment?.currentSemester,
        academicGoal: diagnosticAssessment?.academicGoal,
        confidenceLevel: diagnosticAssessment?.confidenceLevel,
        previousPerformance: diagnosticAssessment?.previousPerformance,
        preferredStudyTime: diagnosticAssessment?.preferredStudyTime,
        // Dashboard-required derived fields
        currentPhase: `Semester ${diagnosticAssessment?.currentSemester || 1}`,
        academicConfidence: ((diagnosticAssessment?.confidenceLevel || 5) / 10),
        socialBattery:
          culturalContext.familySupport === "very-strong" ? "full" :
          culturalContext.familySupport === "limited" ? "low" : "moderate",
        currentMood: wellnessData.sentimentMarker,
        stressLevel: wellnessData.stressIndicator,
      },
      aiPrediction: {},  // will update after FastAPI call
      bloomLevel: mapped.bloomLevel,
      cognitiveRules,
      activeAgents: ["academic"],
    };

    if (!initialProfile) {
      initialProfile = await InitialProfile.create(rawPayload);
    } else {
      await initialProfile.update(rawPayload);
    }

    // ── Step 3: Upsert DiagnosticProfile (structured flat cols) ───
    let diagnosticProfile = await DiagnosticProfile.findOne({ where: { userId } });
    const diagnosticPayload = {
      university: mapped.university,
      program: mapped.program,
      priorEducation: mapped.priorEducation,
      schoolType: mapped.schoolType,
      primaryLanguage: mapped.primaryLanguage,
      englishProficiency: mapped.englishProficiency,
      yearsEnglish: mapped.yearsEnglish,
      previousMedium: mapped.previousMedium,
      studyPace: mapped.studyPace,
      languagePreference: mapped.languagePreference,
      studyHabits: mapped.studyHabits,
      studyHoursPerWeek: mapped.studyHoursPerWeek,
      learningStyles: mapped.learningStyles,
      commuteType: mapped.commuteType,
      techAccess: mapped.techAccess,
      updatedAt: new Date(),
    };

    if (!diagnosticProfile) {
      diagnosticProfile = await DiagnosticProfile.create({ userId, ...diagnosticPayload });
    } else {
      await diagnosticProfile.update(diagnosticPayload);
    }

    // ── Step 4: Seed AcademicProgress rows ────────────────────────
    for (const courseName of mapped.courses) {
      const [progressRow] = await AcademicProgress.findOrCreate({
        where: { userId, courseName },
        defaults: {
          userId,
          courseName,
          currentBloomLevel: mapped.bloomLevel,
          completedTopics: [],
          lastAssessed: new Date(),
        },
      });
      await progressRow.update({
        currentBloomLevel: mapped.bloomLevel,
        lastAssessed: new Date(),
      });
    }

    // ── Step 5: Upsert SocialMetrics ──────────────────────────────
    const [socialMetrics] = await SocialMetrics.findOrCreate({
      where: { userId },
      defaults: { userId, ...socialData },
    });
    await socialMetrics.update({ ...socialData, lastUpdated: new Date() });

    // ── Step 6: Create initial WellnessLog entry ──────────────────
    // Only create if no onboarding wellness log exists yet
    const existingWellness = await WellnessLog.findOne({
      where: { userId, source: "onboarding" },
    });
    if (!existingWellness) {
      await WellnessLog.create({ userId, ...wellnessData });
    }

    // ── Step 7: Call FastAPI ML for predictions ───────────────────
    let mlPrediction = null;
    let wellnessSupportNeeded = wellnessData.stressIndicator >= 0.4;
    let socialSupportNeeded =
      socialData.firstGenStudent ||
      socialData.familySupport === "limited" ||
      (socialData.challenges || []).includes("no-support");
    let languageBarrierRisk = ["beginner", "elementary"].includes(
      educationalBackground.englishProficiency
    ) ? 0.7 : 0.2;

    try {
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
            selfAssessment: {
              currentSemester: diagnosticAssessment?.currentSemester || 1,
              academicGoal: diagnosticAssessment?.academicGoal || "pass-course",
              confidenceLevel: diagnosticAssessment?.confidenceLevel || 5,
              previousPerformance: diagnosticAssessment?.previousPerformance || "average",
              preferredStudyTime: diagnosticAssessment?.preferredStudyTime || "evening",
            },
            userId,
          }),
        },
      );

      if (fastApiResponse.ok) {
        const predictionData = await fastApiResponse.json();
        mlPrediction = predictionData?.prediction || null;

        if (mlPrediction) {
          if (mlPrediction.bloom_level_predicted) {
            mapped.bloomLevel = Number(mlPrediction.bloom_level_predicted);
          }
          if (typeof mlPrediction.language_barrier_risk === "number") {
            languageBarrierRisk = mlPrediction.language_barrier_risk;
          }
          if (typeof mlPrediction.wellness_support_needed === "boolean") {
            wellnessSupportNeeded = mlPrediction.wellness_support_needed;
          }
          if (typeof mlPrediction.social_support_needed === "boolean") {
            socialSupportNeeded = mlPrediction.social_support_needed;
          }
        }
      }
    } catch (mlError) {
      console.warn("FastAPI prediction skipped (using rule-based fallbacks):", mlError.message);
    }

    // ── Step 8: Update InitialProfile with ML outputs ─────────────
    const activeAgents = deriveActiveAgents({
      wellnessSupportNeeded,
      socialSupportNeeded,
      academicSupportNeeded: true,
    });

    await initialProfile.update({
      aiPrediction: {
        ...(mlPrediction || {}),
        ai_prediction: {
          status: "Personalised",
          success_probability: mlPrediction?.success_probability || (
            ((diagnosticAssessment?.confidenceLevel || 5) / 10) * 0.6 +
            (wellnessSupportNeeded ? 0.1 : 0.2) +
            (languageBarrierRisk < 0.4 ? 0.2 : 0.1)
          ),
        },
      },
      bloomLevelPredicted: mapped.bloomLevel,
      bloomLevel: mapped.bloomLevel,
      languageBarrierRisk,
      wellnessSupportNeeded,
      socialSupportNeeded,
      academicSupportNeeded: true,
      cognitiveRules,
      activeAgents,
      // Refresh userProfile with final ML-adjusted values
      userProfile: {
        university: educationalBackground.university,
        program: educationalBackground.program,
        major: educationalBackground.program,
        city: culturalContext.city,
        background: culturalContext.background,
        primaryLanguage: culturalContext.primaryLanguage,
        englishProficiency: educationalBackground.englishProficiency,
        studyPace: learningPreferences.studyPace,
        languagePreference: learningPreferences.languagePreference,
        learningStyles: learningPreferences.learningStyles,
        studyHoursPerWeek: learningPreferences.studyHoursPerWeek,
        strongestSubject: learningPreferences.strongestSubject,
        weakestSubject: learningPreferences.weakestSubject,
        currentSemester: diagnosticAssessment?.currentSemester,
        academicGoal: diagnosticAssessment?.academicGoal,
        confidenceLevel: diagnosticAssessment?.confidenceLevel,
        previousPerformance: diagnosticAssessment?.previousPerformance,
        preferredStudyTime: diagnosticAssessment?.preferredStudyTime,
        currentPhase: `Semester ${diagnosticAssessment?.currentSemester || 1}`,
        academicConfidence: ((diagnosticAssessment?.confidenceLevel || 5) / 10),
        socialBattery:
          culturalContext.familySupport === "very-strong" ? "full" :
          culturalContext.familySupport === "limited" ? "low" : "moderate",
        currentMood: wellnessData.sentimentMarker,
        stressLevel: wellnessData.stressIndicator,
        bloomLevel: mapped.bloomLevel,
        languageBarrierRisk,
        activeAgents,
      },
    });

    // ── Step 9: Initialize Digital Twin (non-fatal) ───────────────
    try {
      await fetch(`${FASTAPI_BASE_URL}/api/digital-twin/initialize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          bloom_level: mapped.bloomLevel,
          language_barrier_risk: languageBarrierRisk,
          initial_predictions: {
            language_barrier_risk: languageBarrierRisk,
            wellness_support_needed: wellnessSupportNeeded,
            social_support_needed: socialSupportNeeded,
            academic_support_needed: true,
          },
        }),
      });
    } catch (twinErr) {
      console.warn("Digital Twin initialization skipped (non-fatal):", twinErr.message);
    }

    // ── Step 10: Embed student profile into pgvector (non-fatal) ──
    // Fires as a background task in FastAPI — does not block the response.
    try {
      const rawProfileText = [
        `University: ${educationalBackground.university || ""}`,
        `Program: ${educationalBackground.program || ""}`,
        `Prior Education: ${educationalBackground.priorEducation || ""}`,
        `School Type: ${educationalBackground.schoolType || ""}`,
        `Primary Language: ${culturalContext.primaryLanguage || ""}`,
        `English Proficiency: ${educationalBackground.englishProficiency || ""}`,
        `Study Pace: ${learningPreferences.studyPace || ""}`,
        `Learning Styles: ${(learningPreferences.learningStyles || []).join(", ")}`,
        `Courses: ${(mapped.courses || []).join(", ")}`,
        `Bloom Level: ${mapped.bloomLevel}`,
        `Language Barrier Risk: ${languageBarrierRisk}`,
        `Wellness Support Needed: ${wellnessSupportNeeded}`,
        `Social Support Needed: ${socialSupportNeeded}`,
        `City: ${culturalContext.city || ""}`,
        `Family Pressure: ${culturalContext.familyPressure || ""}`,
        `Study Hours Per Week: ${learningPreferences.studyHoursPerWeek || ""}`,
        `Tech Access: ${learningPreferences.techAccess || ""}`,
        `Commute Type: ${learningPreferences.commuteType || ""}`,
      ].join("\n");

      await fetch(`${FASTAPI_BASE_URL}/api/agent/onboarding/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, raw_profile_text: rawProfileText }),
      });
    } catch (embedErr) {
      console.warn("Profile vector embedding skipped (non-fatal):", embedErr.message);
    }

    // ── Return dashboard-ready payload ────────────────────────────
    return res.status(200).json({
      success: true,
      userId,
      persistentLearnerId: initialProfile.profileId,
      studentProfile: {
        educationalBackground,
        learningPreferences,
        culturalContext,
        diagnosticAssessment,
      },
      diagnosticProfile: {
        university: diagnosticProfile.university,
        program: diagnosticProfile.program,
        priorEducation: diagnosticProfile.priorEducation,
        primaryLanguage: diagnosticProfile.primaryLanguage,
        englishProficiency: diagnosticProfile.englishProficiency,
        commuteType: diagnosticProfile.commuteType,
        techAccess: diagnosticProfile.techAccess,
      },
      academicProfile: {
        bloomLevel: mapped.bloomLevel,
        courses: mapped.courses,
      },
      socialProfile: {
        firstGenStudent: socialMetrics.firstGenStudent,
        familySupport: socialMetrics.familySupport,
        communicationScore: socialMetrics.communicationScore,
        challenges: socialMetrics.challenges,
      },
      wellnessProfile: {
        sentimentMarker: wellnessData.sentimentMarker,
        stressIndicator: wellnessData.stressIndicator,
        familyPressure: wellnessData.familyPressure,
      },
      aiPrediction: mlPrediction,
      cognitiveRules,
      activeAgents,
      languageBarrierRisk,
      wellnessSupportNeeded,
      socialSupportNeeded,
      pipeline: [
        "form_received",
        "initial_profile_saved",
        "diagnostic_profile_saved",
        "academic_progress_seeded",
        "social_metrics_seeded",
        "wellness_log_created",
        mlPrediction ? "ml_prediction_applied" : "ml_skipped_using_rules",
        "digital_twin_initialized",
        "profile_embedding_queued",
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

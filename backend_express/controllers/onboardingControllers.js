import db from "../model/index.js";

const { User, InitialProfile } = db;

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

    // Call FastAPI backend for ML predictions
    const fastApiResponse = await fetch(
      "http://localhost:8000/api/predict/initial-profile",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
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

    await InitialProfile.upsert({
      userId,
      educationalBackground,
      learningPreferences,
      culturalContext,
      diagnosticAssessment: diagnosticAssessment || {},
      userProfile,
      aiPrediction,
    });

    if (!user.isOnboarded) {
      user.isOnboarded = true;
      await user.save();
    }

    // Consolidate response with both student profile and ML predictions
    return res.status(200).json({
      userId,
      persistentLearnerId: predictionData.persistentLearnerId,
      studentProfile: {
        educationalBackground,
        learningPreferences,
        culturalContext,
        diagnosticAssessment: diagnosticAssessment || {},
      },
      aiPrediction: predictionData.prediction,
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

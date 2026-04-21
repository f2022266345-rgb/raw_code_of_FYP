import db from "../model/index.js";

const { InitialProfile } = db;

/**
 * POST /api/chat
 * Receives a student message and agent type, fetches the student's context from DB,
 * then calls the FastAPI /api/chat endpoint (which runs the LLM) and returns the response.
 */
const chatWithAgent = async (req, res) => {
  try {
    const { userId } = req.user;
    const { message, agentType, chatHistory } = req.body;

    if (!message || !agentType) {
      return res.status(400).json({ message: "message and agentType are required" });
    }

    const validAgents = ["academic", "wellness", "social", "coordinator", "tutor"];
    if (!validAgents.includes(agentType)) {
      return res.status(400).json({ message: `Invalid agentType. Must be one of: ${validAgents.join(", ")}` });
    }

    // Fetch student profile for context injection into the LLM prompt
    const profile = await InitialProfile.findOne({ where: { userId } });
    const userProfile = profile?.userProfile || {};
    const bloomLevel = profile?.bloomLevel ?? 2;
    const languageBarrierRisk = profile?.languageBarrierRisk ?? 0.2;
    const learningPrefs = profile?.learningPreferences || {};

    const studentContext = {
      name: userProfile.name || "Student",
      major: userProfile.major || "Computer Science",
      university: userProfile.university || "University",
      bloom_level: bloomLevel,
      language_barrier_risk: languageBarrierRisk,
      stress_level: userProfile.stressLevel ?? 4,
      social_battery: userProfile.socialBattery ?? "moderate",
      language_preference: learningPrefs.languagePreference ?? "english-only",
    };

    // Call FastAPI LLM service
    const faResponse = await fetch("http://localhost:8000/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent_type: agentType,
        message,
        student_context: studentContext,
        chat_history: chatHistory || [],
      }),
    });

    if (!faResponse.ok) {
      const errorData = await faResponse.json();
      console.error("FastAPI chat error:", errorData);
      return res.status(500).json({ message: "Chat service unavailable", error: errorData });
    }

    const chatData = await faResponse.json();

    return res.status(200).json({
      agent: agentType,
      response: chatData.response,
      studentContext: {
        bloomLevel,
        languageBarrierRisk,
      },
    });
  } catch (error) {
    console.error("chatWithAgent error:", error);
    return res.status(500).json({ message: "Chat failed", error: error.message });
  }
};

export default { chatWithAgent };

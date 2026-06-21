import db from "../model/index.js";
import { Op } from "sequelize";

const {
  User,
  DiagnosticProfile,
  AcademicProgress,
  SocialMetrics,
  WellnessLog,
  ChatThread,
  ChatMessage,
  InitialProfile,
  BktSkillMastery,
  StudentProfileState,
  StudentInteraction,
} = db;

const getMyDashboard = async (req, res) => {
  try {
    const { userId } = req.user;

    const user = await User.findOne({ where: { id: userId } });
    if (!user) {
      return res.status(404).json({ message: "User not found" });
    }

    const diagnosticProfile = await DiagnosticProfile.findOne({ where: { userId } });
    const academicProgress = await AcademicProgress.findAll({
      where: { userId },
      order: [["lastAssessed", "DESC NULLS LAST"]],
    });
    const socialMetrics = await SocialMetrics.findOne({ where: { userId } });
    const wellnessLogs = await WellnessLog.findAll({
      where: { userId },
      order: [["loggedAt", "DESC"]],
      limit: 10,
    });

    const threads = await ChatThread.findAll({
      where: { userId },
      order: [["createdAt", "DESC"]],
      limit: 5,
    });
    const threadIds = threads.map((t) => t.id);

    const recentMessages = threadIds.length
      ? await ChatMessage.findAll({
          where: { threadId: { [Op.in]: threadIds } },
          order: [["createdAt", "DESC"]],
          limit: 40,
        })
      : [];

    const initialProfile = await InitialProfile.findOne({ where: { userId } });
    const bktSkills = await BktSkillMastery.findAll({ where: { userId } });
    const hiddenStateRecord = await StudentProfileState.findOne({ 
      where: { userId },
      order: [["createdAt", "DESC"]]
    });
    const recentInteractions = await StudentInteraction.findAll({
      where: { userId },
      order: [["occurredAt", "DESC"]],
      limit: 10
    });

    const chatHistory = recentMessages
      .slice()
      .reverse()
      .map((msg) => ({
        role: msg.sender === "user" ? "user" : "assistant",
        content: msg.messageText,
        occurredAt: msg.createdAt,
        agent: msg.sender,
        uiCardMetadata: msg.uiCardMetadata,
      }));

    const latestWellness = wellnessLogs[0] || null;
    const latestChat = recentMessages[0] || null;

    return res.status(200).json({
      user: {
        userId: user.id,
        name: user.fullName,
        email: user.email,
        clerkId: user.clerkId,
        isOnboarded: Boolean(diagnosticProfile),
        createdAt: user.createdAt,
        // Derived from stored userProfile for dashboard display
        stressLevel: initialProfile?.userProfile?.stressLevel ?? 0,
        currentMood: initialProfile?.userProfile?.currentMood ?? "Neutral",
        currentPhase: initialProfile?.userProfile?.currentPhase ?? "",
        academicConfidence: initialProfile?.userProfile?.academicConfidence ?? 0,
        socialBattery: initialProfile?.userProfile?.socialBattery ?? "moderate",
      },
      onboardingCompleted: Boolean(diagnosticProfile),
      diagnosticProfile: diagnosticProfile
        ? {
            priorEducation: diagnosticProfile.priorEducation,
            primaryLanguage: diagnosticProfile.primaryLanguage,
            commuteType: diagnosticProfile.commuteType,
            techAccess: diagnosticProfile.techAccess,
            updatedAt: diagnosticProfile.updatedAt,
          }
        : null,
      academicProgress: academicProgress.map((row) => ({
        id: row.id,
        courseName: row.courseName,
        currentBloomLevel: row.currentBloomLevel,
        completedTopics: row.completedTopics,
        lastAssessed: row.lastAssessed,
      })),
      socialMetrics: socialMetrics
        ? {
            linkedinOptimized: socialMetrics.linkedinOptimized,
            instagramOptimized: socialMetrics.instagramOptimized,
            communicationScore: socialMetrics.communicationScore,
            lastUpdated: socialMetrics.lastUpdated,
          }
        : null,
      wellnessSummary: {
        latestSentiment: latestWellness?.sentimentMarker || null,
        recentLogs: wellnessLogs.map((log) => ({
          sentimentMarker: log.sentimentMarker,
          nearestClinicId: log.nearestClinicId,
          loggedAt: log.loggedAt,
        })),
      },
      chatThreads: threads.map((thread) => ({
        id: thread.id,
        currentRoutingAgent: thread.currentRoutingAgent,
        createdAt: thread.createdAt,
      })),
      chatHistorySummary: {
        totalMessages: recentMessages.length,
        userMessages: recentMessages.filter(m => m.sender === 'user').length,
        assistantMessages: recentMessages.filter(m => m.sender !== 'user').length,
        lastMessageAt: latestChat?.createdAt || null,
        lastMessage: latestChat?.messageText || null,
        lastAgent: latestChat?.sender || null,
      },
      chatHistory,
      
      // Data required for frontend dashboard features
      aiPrediction: initialProfile ? {
        ai_prediction: initialProfile.aiPrediction?.ai_prediction || {
          status: "Personalised",
          success_probability: 0.7,
        },
        user_profile: {
          // Spread stored userProfile for all dashboard-readable fields
          ...(initialProfile.userProfile || {}),
          // Ensure required dashboard fields always present
          major: initialProfile.userProfile?.major || initialProfile.userProfile?.program || "",
          university: initialProfile.userProfile?.university || "",
          stressLevel: initialProfile.userProfile?.stressLevel ?? 0,
          currentMood: initialProfile.userProfile?.currentMood ?? "Neutral",
          currentPhase: initialProfile.userProfile?.currentPhase ?? "",
          academicConfidence: initialProfile.userProfile?.academicConfidence ?? 0,
          socialBattery: initialProfile.userProfile?.socialBattery ?? "moderate",
        },
        bloomLevel: initialProfile.bloomLevel || 1,
        languageBarrierRisk: initialProfile.languageBarrierRisk || 0,
        activeAgents: initialProfile.activeAgents || ["academic"],
      } : null,
      
      bktSummary: {
        totalSkills: bktSkills.length,
        avgMastery: bktSkills.length ? bktSkills.reduce((acc, s) => acc + (s.pMastery || 0), 0) / bktSkills.length * 100 : 0,
        masteredCount: bktSkills.filter(s => (s.pMastery || 0) > 0.8).length,
        needsAttentionCount: bktSkills.filter(s => (s.pMastery || 0) < 0.4).length,
        weakestSkills: bktSkills.sort((a, b) => (a.pMastery || 0) - (b.pMastery || 0)).slice(0, 5).map(s => ({
          name: s.skillName,
          mastery: (s.pMastery || 0) * 100
        }))
      },
      
      hiddenState: hiddenStateRecord ? {
        accuracyTrendSlope: hiddenStateRecord.accuracyTrendSlope,
        timeTrendSlope: hiddenStateRecord.timeTrendSlope,
        hintTrendSlope: hiddenStateRecord.hintTrendSlope,
        frustrationEstimate: hiddenStateRecord.frustrationEstimate,
        engagementEstimate: hiddenStateRecord.engagementEstimate,
        readinessEstimate: hiddenStateRecord.readinessEstimate,
      } : {
        accuracyTrendSlope: 0,
        timeTrendSlope: 0,
        hintTrendSlope: 0,
        frustrationEstimate: 0,
        engagementEstimate: 0,
        readinessEstimate: 0
      },
      
      coordinatorRoutingHistory: recentInteractions.map(log => ({
        occurredAt: log.occurredAt,
        sourceEventType: log.eventType,
        routedAgent: log.metadata?.agent || "coordinator",
        matchedRule: log.metadata?.rule || "Default routing",
        rationale: log.metadata?.rationale || ""
      })),
      
      observations: {
        totalEvents: recentInteractions.length,
        totalTimeOnPageMs: recentInteractions.reduce((acc, log) => acc + (log.sessionTimeSpentMs || 0), 0),
        totalClicks: 0,
        averageResponseTimeMs: recentInteractions.length > 0
          ? recentInteractions.reduce((acc, log) => acc + (log.responseTimeMs || 0), 0) / recentInteractions.length
          : null,
        latestMood: recentInteractions.find(l => l.metadata?.mood)?.metadata?.mood || null,
        latestConfidence: recentInteractions.find(l => l.metadata?.confidence != null)?.metadata?.confidence || null,
      },
      
      agentsStatus: {
        isAnalyzing: false,
        academic: (initialProfile?.activeAgents || []).includes("academic") ? "active" : "idle",
        social: (initialProfile?.activeAgents || []).includes("social") ? "active" : "idle",
        wellness: (initialProfile?.activeAgents || []).includes("wellness") ? "active" : "idle"
      },
      
      agentResults: {
        academic: bktSkills.length > 0 
          ? `Tracking ${bktSkills.length} skills. Avg mastery: ${Math.round(bktSkills.reduce((acc, s) => acc + (s.pMastery || 0), 0) / bktSkills.length * 100)}%`
          : "Ready to track your academic progress.",
        social: socialMetrics 
          ? `Communication score: ${socialMetrics.communicationScore}/100` 
          : "Ready to support your social connections.",
        wellness: latestWellness 
          ? `Latest sentiment: ${latestWellness.sentimentMarker}` 
          : "Monitoring your well-being."
      }
    });
  } catch (error) {
    console.error("Dashboard fetch error:", error);
    return res.status(500).json({ message: "Failed to load dashboard" });
  }
};

export default { getMyDashboard };

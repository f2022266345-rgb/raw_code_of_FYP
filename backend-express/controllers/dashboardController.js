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
        lastMessageAt: latestChat?.createdAt || null,
        lastMessage: latestChat?.messageText || null,
        lastAgent: latestChat?.sender || null,
      },
      chatHistory,
    });
  } catch (error) {
    console.error("Dashboard fetch error:", error);
    return res.status(500).json({ message: "Failed to load dashboard" });
  }
};

export default { getMyDashboard };

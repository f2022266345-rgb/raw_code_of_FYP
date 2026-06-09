import db from "../model/index.js";

const { AcademicProgress } = db;

/**
 * Legacy /api/bkt routes mapped onto academic_progress rows.
 */
const getUserSkills = async (req, res) => {
  try {
    const { userId } = req.user;
    const rows = await AcademicProgress.findAll({
      where: { userId },
      order: [["currentBloomLevel", "ASC"]],
    });

    if (!rows.length) {
      return res.status(200).json({
        message: "No academic progress found. Complete onboarding to initialize.",
        skills: [],
        summary: {
          totalSkills: 0,
          avgMastery: 0,
          masteredCount: 0,
          needsAttentionCount: 0,
        },
      });
    }

    const skills = rows.map((row) => {
      const masteryPct = Math.round((row.currentBloomLevel / 6) * 100);
      return {
        name: row.courseName,
        category: "Course",
        mastery: masteryPct,
        pMastery: row.currentBloomLevel / 6,
        practiceCount: row.completedTopics.length,
        lastPracticedAt: row.lastAssessed,
        trend: row.currentBloomLevel >= 4 ? "up" : "stable",
        completedTopics: row.completedTopics,
      };
    });

    const avgMastery =
      skills.reduce((sum, s) => sum + s.mastery, 0) / skills.length;
    const masteredCount = skills.filter((s) => s.mastery >= 80).length;
    const needsAttentionCount = skills.filter((s) => s.mastery < 50).length;

    return res.status(200).json({
      skills,
      summary: {
        totalSkills: skills.length,
        avgMastery: Number(avgMastery.toFixed(1)),
        masteredCount,
        needsAttentionCount,
      },
    });
  } catch (error) {
    console.error("getUserSkills error:", error);
    return res.status(500).json({ message: "Failed to retrieve academic progress" });
  }
};

const updateSkillMastery = async (req, res) => {
  try {
    const { userId } = req.user;
    const courseName = decodeURIComponent(req.params.skillName);
    const { correct, topic } = req.body;

    const row = await AcademicProgress.findOne({ where: { userId, courseName } });
    if (!row) {
      return res.status(404).json({
        message: `Course '${courseName}' not found for this user`,
      });
    }

    const prevLevel = row.currentBloomLevel;
    let newLevel = prevLevel;
    if (correct === true && prevLevel < 6) newLevel = prevLevel + 1;
    if (correct === false && prevLevel > 1) newLevel = prevLevel - 1;

    const completedTopics = [...row.completedTopics];
    if (correct === true && topic && !completedTopics.includes(topic)) {
      completedTopics.push(String(topic));
    }

    await row.update({
      currentBloomLevel: newLevel,
      completedTopics,
      lastAssessed: new Date(),
    });

    return res.status(200).json({
      skillName: courseName,
      prevMastery: Math.round((prevLevel / 6) * 100),
      newMastery: Math.round((newLevel / 6) * 100),
      correct,
      masteryChange: Math.round(((newLevel - prevLevel) / 6) * 100),
    });
  } catch (error) {
    console.error("updateSkillMastery error:", error);
    return res.status(500).json({ message: "Failed to update academic progress" });
  }
};

const analyzeState = async (req, res) => {
  try {
    const { userId } = req.user;
    const { WellnessLog } = db;
    const logs = await WellnessLog.findAll({
      where: { userId },
      order: [["loggedAt", "DESC"]],
      limit: 5,
    });

    const state =
      logs[0]?.sentimentMarker === "Stressed"
        ? "CRITICAL_STRUGGLE"
        : logs[0]?.sentimentMarker === "Stable"
          ? "FLOW_STATE"
          : "NEUTRAL";

    return res.status(200).json({
      state,
      signals: {
        recentWellnessMarkers: logs.map((l) => l.sentimentMarker),
      },
      eventsAnalyzed: logs.length,
    });
  } catch (error) {
    console.error("analyzeState error:", error);
    return res.status(500).json({ message: "Failed to analyze cognitive state" });
  }
};

export default { getUserSkills, updateSkillMastery, analyzeState };

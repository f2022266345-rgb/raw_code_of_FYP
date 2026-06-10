/**
 * cronJobs.js — Bi-weekly monitoring loop (BPMN TIMER_2_WEEKS node)
 *
 * Every day at midnight:
 *   1. Finds users who have hit a 14-day milestone (14, 28, 42... days since onboarding)
 *   2. Calls FastAPI /api/agent/metrics/analyze — runs the semester LangGraph
 *   3. If result is "Critical" → creates a CounselorCase for human review
 *   4. If result is "OK"       → Bloom level was already updated by FastAPI
 */

import cron from "node-cron";
import db from "../model/index.js";

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || "http://localhost:8080";

const _postFastApi = async (path, payload) => {
  const response = await fetch(`${FASTAPI_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`FastAPI ${path} → ${response.status}: ${text}`);
  }
  return response.json();
};

// ─── Bi-weekly milestone check — runs daily at 00:05 ──────────────────────────
cron.schedule("5 0 * * *", async () => {
  console.log("[Cron] Running daily 2-week milestone check...");
  try {
    const users = await db.User.findAll({ attributes: ["id", "createdAt"] });
    const now = new Date();

    for (const user of users) {
      if (!user.createdAt) continue;

      const diffDays = Math.floor(
        Math.abs(now - new Date(user.createdAt)) / (1000 * 60 * 60 * 24),
      );

      // Only trigger on exact 2-week multiples (14, 28, 42 days...)
      if (diffDays < 14 || diffDays % 14 !== 0) continue;

      console.log(
        `[Cron] User ${user.id} hit day-${diffDays} milestone. Running analysis...`,
      );

      try {
        const result = await _postFastApi("/api/agent/metrics/analyze", {
          user_id: user.id,
        });

        console.log(
          `[Cron] Analysis for user ${user.id}: status=${result.status}`,
        );

        if (result.status === "Critical") {
          // Create a counselor case for human review
          const existing = await db.CounselorCase.findOne({
            where: {
              userId: user.id,
              status: { [db.sequelize.Op?.ne || "ne"]: "resolved" },
              triggerSource: "biweekly_cron",
            },
          });

          if (!existing) {
            await db.CounselorCase.create({
              userId: user.id,
              triggerSource: "biweekly_cron",
              severity: "Critical",
              status: "open",
              aiAnalysis: result.analysis || "Critical performance degradation detected.",
              progressData: result.progress_data || {},
            });
            console.log(
              `[Cron] ✅ Counselor case created for user ${user.id} (Critical)`,
            );
          } else {
            console.log(
              `[Cron] ℹ️  Open counselor case already exists for user ${user.id}`,
            );
          }
        } else {
          console.log(
            `[Cron] ✅ User ${user.id} is OK. Bloom level updated by FastAPI.`,
          );
        }
      } catch (apiErr) {
        console.error(
          `[Cron] FastAPI analysis failed for user ${user.id}:`,
          apiErr.message,
        );
      }
    }
  } catch (err) {
    console.error("[Cron] Error running milestone check:", err);
  }
});

// ─── Wellness escalation helper (called from chatController) ──────────────────
/**
 * Creates an urgent CounselorCase when the Wellness Agent detects a critical keyword.
 * Can be imported and called directly from controllers.
 */
export const createWellnessEscalation = async (userId, analysisText = "") => {
  try {
    const existing = await db.CounselorCase.findOne({
      where: {
        userId,
        triggerSource: "wellness_agent",
        status: ["open", "in_review"],
      },
    });

    if (existing) return existing; // don't duplicate

    const newCase = await db.CounselorCase.create({
      userId,
      triggerSource: "wellness_agent",
      severity: "Critical",
      status: "open",
      aiAnalysis:
        analysisText ||
        "Critical mental health indicator detected in conversation.",
    });

    console.log(
      `[Wellness Escalation] Counselor case created for user ${userId}`,
    );
    return newCase;
  } catch (err) {
    console.error("[Wellness Escalation] Failed to create case:", err);
    return null;
  }
};

console.log("[Cron] Cron jobs initialized (bi-weekly monitoring active).");

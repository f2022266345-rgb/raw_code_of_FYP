import db from "../model/index.js";
import { Op } from "sequelize";

const { CounselorCase, User, InitialProfile } = db;

const FASTAPI_BASE_URL =
  process.env.FASTAPI_BASE_URL || "http://localhost:8080";

// ─── Helper ───────────────────────────────────────────────────────────────────
const _postFastApiJson = async (path, payload) => {
  const response = await fetch(`${FASTAPI_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`FastAPI ${path} failed (${response.status}): ${text}`);
  }
  return response.json();
};

// ─── GET /api/counselor/cases ─────────────────────────────────────────────────
/**
 * Returns all counselor cases, optionally filtered by status or severity.
 * Used by the counselor dashboard to show the case queue.
 */
const listCases = async (req, res) => {
  try {
    const { status, severity, userId, limit = "50", page = "1" } = req.query;
    const safeLimit = Math.min(Math.max(Number(limit) || 50, 1), 200);
    const safePage = Math.max(Number(page) || 1, 1);
    const offset = (safePage - 1) * safeLimit;

    const where = {};
    if (status) where.status = status;
    if (severity) where.severity = severity;
    if (userId) where.userId = userId;

    const { rows, count } = await CounselorCase.findAndCountAll({
      where,
      limit: safeLimit,
      offset,
      order: [["createdAt", "DESC"]],
      include: [
        {
          model: User,
          as: "student",
          attributes: ["id", "fullName", "email"],
          required: false,
        },
      ],
    });

    return res.status(200).json({
      cases: rows,
      total: count,
      page: safePage,
      totalPages: Math.ceil(count / safeLimit),
    });
  } catch (error) {
    console.error("listCases error:", error);
    return res.status(500).json({ message: "Failed to fetch counselor cases" });
  }
};

// ─── GET /api/counselor/cases/:caseId ────────────────────────────────────────
/**
 * Returns a single case with full student profile context.
 */
const getCase = async (req, res) => {
  try {
    const { caseId } = req.params;

    const counselorCase = await CounselorCase.findByPk(caseId, {
      include: [
        {
          model: User,
          as: "student",
          attributes: ["id", "fullName", "email"],
        },
      ],
    });

    if (!counselorCase) {
      return res.status(404).json({ message: "Case not found" });
    }

    // Fetch student's initial profile for extra context
    const profile = await InitialProfile.findOne({
      where: { userId: counselorCase.userId },
    });

    return res.status(200).json({
      case: counselorCase,
      studentProfile: profile || null,
    });
  } catch (error) {
    console.error("getCase error:", error);
    return res.status(500).json({ message: "Failed to fetch case" });
  }
};

// ─── PATCH /api/counselor/cases/:caseId ──────────────────────────────────────
/**
 * Counselor reviews a case:
 * - Adds notes
 * - Changes status (open → in_review → resolved / escalated)
 * - Optionally updates student AI parameters (pacing, languageSupport, etc.)
 *   which are then forwarded to FastAPI for real-time effect on tutoring
 */
const updateCase = async (req, res) => {
  try {
    const { caseId } = req.params;
    const { counselorNotes, status, severity, parameterUpdates } = req.body;

    const counselorCase = await CounselorCase.findByPk(caseId);
    if (!counselorCase) {
      return res.status(404).json({ message: "Case not found" });
    }

    const updates = {};
    if (counselorNotes !== undefined) updates.counselorNotes = counselorNotes;
    if (status !== undefined) updates.status = status;
    if (severity !== undefined) updates.severity = severity;
    if (parameterUpdates !== undefined)
      updates.parameterUpdates = parameterUpdates;
    if (status === "resolved") updates.resolvedAt = new Date();

    await counselorCase.update(updates);

    // ── If counselor provided parameter updates, forward to FastAPI ──────
    if (parameterUpdates && Object.keys(parameterUpdates).length > 0) {
      try {
        await _postFastApiJson("/api/agent/counselor/apply-updates", {
          user_id: counselorCase.userId,
          updates: parameterUpdates,
          case_id: caseId,
          counselor_notes: counselorNotes || "",
        });
        console.log(
          `[Counselor] Parameter updates forwarded to FastAPI for user ${counselorCase.userId}`,
        );
      } catch (fastapiErr) {
        console.error(
          "[Counselor] Failed to forward updates to FastAPI:",
          fastapiErr.message,
        );
        // Non-fatal — case is still updated in DB
      }
    }

    return res.status(200).json({
      message: "Case updated successfully",
      case: counselorCase,
    });
  } catch (error) {
    console.error("updateCase error:", error);
    return res.status(500).json({ message: "Failed to update case" });
  }
};

// ─── GET /api/counselor/stats ─────────────────────────────────────────────────
/**
 * Dashboard summary stats for the counselor portal.
 */
const getDashboardStats = async (req, res) => {
  try {
    const [open, inReview, resolved, critical] = await Promise.all([
      CounselorCase.count({ where: { status: "open" } }),
      CounselorCase.count({ where: { status: "in_review" } }),
      CounselorCase.count({ where: { status: "resolved" } }),
      CounselorCase.count({ where: { severity: "Critical" } }),
    ]);

    // Recent 5 open cases
    const recentCases = await CounselorCase.findAll({
      where: { status: { [Op.in]: ["open", "in_review"] } },
      order: [["createdAt", "DESC"]],
      limit: 5,
      include: [
        {
          model: User,
          as: "student",
          attributes: ["id", "fullName", "email"],
          required: false,
        },
      ],
    });

    return res.status(200).json({
      stats: { open, inReview, resolved, critical },
      recentCases,
    });
  } catch (error) {
    console.error("getDashboardStats error:", error);
    return res.status(500).json({ message: "Failed to fetch dashboard stats" });
  }
};

// ─── POST /api/counselor/cases (manual creation) ──────────────────────────────
/**
 * Allows a counselor to manually open a case for a student.
 */
const createCase = async (req, res) => {
  try {
    const { userId, triggerSource = "manual", severity = "Standard", notes } =
      req.body;

    if (!userId) {
      return res.status(400).json({ message: "userId is required" });
    }

    const newCase = await CounselorCase.create({
      userId,
      triggerSource,
      severity,
      status: "open",
      counselorNotes: notes || null,
    });

    return res.status(201).json({ message: "Case created", case: newCase });
  } catch (error) {
    console.error("createCase error:", error);
    return res.status(500).json({ message: "Failed to create case" });
  }
};

export default { listCases, getCase, updateCase, getDashboardStats, createCase };

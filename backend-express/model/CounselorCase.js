import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

/**
 * CounselorCase — Human Support Services layer (BPMN Lane 8)
 *
 * Created automatically when:
 *  - bi-weekly metrics analysis flags a student as "Critical"
 *  - Wellness agent detects a critical mental health indicator
 *
 * Reviewed and actioned by a human counselor.
 */
const CounselorCase = sequelize.define(
  "CounselorCase",
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
      allowNull: false,
    },
    userId: {
      type: DataTypes.UUID,
      allowNull: false,
      field: "user_id",
      references: { model: "users", key: "id" },
      onDelete: "CASCADE",
    },

    // ── Case classification ──────────────────────────────────────────
    triggerSource: {
      type: DataTypes.STRING(50),
      allowNull: false,
      defaultValue: "biweekly_cron",
      field: "trigger_source",
      // 'biweekly_cron' | 'wellness_agent' | 'academic_agent' | 'manual'
    },
    severity: {
      type: DataTypes.STRING(20),
      allowNull: false,
      defaultValue: "Standard",
      field: "severity",
      // 'Standard' | 'High' | 'Critical'
    },
    status: {
      type: DataTypes.STRING(20),
      allowNull: false,
      defaultValue: "open",
      field: "status",
      // 'open' | 'in_review' | 'resolved' | 'escalated'
    },

    // ── AI-generated analysis ────────────────────────────────────────
    aiAnalysis: {
      type: DataTypes.TEXT,
      allowNull: true,
      field: "ai_analysis",
    },
    progressData: {
      type: DataTypes.JSONB,
      allowNull: true,
      field: "progress_data",
      // { grades, attendance_rate, total_interactions, ... }
    },

    // ── Counselor actions ────────────────────────────────────────────
    counselorNotes: {
      type: DataTypes.TEXT,
      allowNull: true,
      field: "counselor_notes",
    },
    parameterUpdates: {
      type: DataTypes.JSONB,
      allowNull: true,
      field: "parameter_updates",
      // { pacing: 'slow', languageSupport: true, ... }
    },
    resolvedAt: {
      type: DataTypes.DATE,
      allowNull: true,
      field: "resolved_at",
    },
  },
  {
    timestamps: true,
    tableName: "counselor_cases",
  },
);

export default CounselorCase;

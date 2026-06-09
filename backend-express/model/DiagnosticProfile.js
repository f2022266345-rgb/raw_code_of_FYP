import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const DiagnosticProfile = sequelize.define(
  "DiagnosticProfile",
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
      unique: true,
      field: "user_id",
      references: { model: "users", key: "id" },
      onDelete: "CASCADE",
    },

    // ── Educational Info ────────────────────────────────────────────
    university: {
      type: DataTypes.STRING(120),
      allowNull: true,
      field: "university",
    },
    program: {
      type: DataTypes.STRING(120),
      allowNull: true,
      field: "program",
    },
    priorEducation: {
      type: DataTypes.STRING(120),
      allowNull: true,
      field: "prior_education",
    },
    schoolType: {
      type: DataTypes.STRING(80),
      allowNull: true,
      field: "school_type",
    },

    // ── Language ────────────────────────────────────────────────────
    primaryLanguage: {
      type: DataTypes.STRING(80),
      allowNull: true,
      field: "primary_language",
    },
    englishProficiency: {
      type: DataTypes.STRING(50),
      allowNull: true,
      field: "english_proficiency",
    },
    yearsEnglish: {
      type: DataTypes.INTEGER,
      allowNull: true,
      field: "years_english",
    },
    previousMedium: {
      type: DataTypes.ARRAY(DataTypes.TEXT),
      allowNull: true,
      defaultValue: [],
      field: "previous_medium",
    },

    // ── Learning Style ──────────────────────────────────────────────
    studyPace: {
      type: DataTypes.STRING(50),
      allowNull: true,
      field: "study_pace",
    },
    languagePreference: {
      type: DataTypes.STRING(80),
      allowNull: true,
      field: "language_preference",
    },
    studyHabits: {
      type: DataTypes.STRING(50),
      allowNull: true,
      field: "study_habits",
    },
    studyHoursPerWeek: {
      type: DataTypes.INTEGER,
      allowNull: true,
      field: "study_hours_per_week",
    },
    learningStyles: {
      type: DataTypes.JSONB,
      allowNull: true,
      defaultValue: {},
      field: "learning_styles",
    },

    // ── Infrastructure ──────────────────────────────────────────────
    commuteType: {
      type: DataTypes.STRING(80),
      allowNull: true,
      field: "commute_type",
    },
    techAccess: {
      type: DataTypes.STRING(80),
      allowNull: true,
      field: "tech_access",
    },

    updatedAt: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
      field: "updated_at",
    },
  },
  {
    timestamps: false,
    tableName: "diagnostic_profiles",
  },
);

export default DiagnosticProfile;

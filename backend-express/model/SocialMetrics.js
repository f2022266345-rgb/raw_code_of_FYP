import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const SocialMetrics = sequelize.define(
  "SocialMetrics",
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

    // ── Baseline social flags from onboarding ──────────────────────
    firstGenStudent: {
      type: DataTypes.BOOLEAN,
      allowNull: true,
      defaultValue: false,
      field: "first_gen_student",
    },
    familySupport: {
      type: DataTypes.STRING(50),
      allowNull: true,
      field: "family_support",  // 'very-strong' | 'moderate' | 'limited'
    },
    city: {
      type: DataTypes.STRING(120),
      allowNull: true,
      field: "city",
    },
    background: {
      type: DataTypes.STRING(50),
      allowNull: true,
      field: "background",  // 'urban' | 'semi-urban' | 'rural'
    },
    challenges: {
      type: DataTypes.ARRAY(DataTypes.TEXT),
      allowNull: true,
      defaultValue: [],
      field: "challenges",
    },
    learningContext: {
      type: DataTypes.ARRAY(DataTypes.TEXT),
      allowNull: true,
      defaultValue: [],
      field: "learning_context",
    },

    // ── Computed / ongoing metrics ─────────────────────────────────
    communicationScore: {
      type: DataTypes.INTEGER,
      allowNull: false,
      defaultValue: 50,
      field: "communication_score",
      validate: { min: 0, max: 100 },
    },
    linkedinOptimized: {
      type: DataTypes.BOOLEAN,
      allowNull: false,
      defaultValue: false,
      field: "linkedin_optimized",
    },
    instagramOptimized: {
      type: DataTypes.BOOLEAN,
      allowNull: false,
      defaultValue: false,
      field: "instagram_optimized",
    },
    lastUpdated: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
      field: "last_updated",
    },
  },
  {
    timestamps: false,
    tableName: "social_metrics",
  },
);

export default SocialMetrics;

import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const InitialProfile = sequelize.define(
  "InitialProfile",
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    profileId: {
      type: DataTypes.UUID,
      defaultValue: DataTypes.UUIDV4,
      allowNull: false,
      unique: true,
    },
    // Persistent Learner ID returned by FastAPI
    persistentLearnerId: {
      type: DataTypes.UUID,
      allowNull: true,
      field: "persistent_learner_id",
    },
    userId: {
      type: DataTypes.UUID,
      allowNull: false,
      unique: true,
      field: "user_id",
    },
    educationalBackground: {
      type: DataTypes.JSONB,
      allowNull: false,
      field: "educational_background",
    },
    learningPreferences: {
      type: DataTypes.JSONB,
      allowNull: false,
      field: "learning_preferences",
    },
    culturalContext: {
      type: DataTypes.JSONB,
      allowNull: false,
      field: "cultural_context",
    },
    diagnosticAssessment: {
      type: DataTypes.JSONB,
      allowNull: true,
      field: "diagnostic_assessment",
    },
    userProfile: {
      type: DataTypes.JSONB,
      allowNull: false,
      field: "user_profile",
    },
    aiPrediction: {
      type: DataTypes.JSONB,
      allowNull: false,
      field: "ai_prediction",
    },
    // Extracted ML outputs stored as flat columns for easy querying
    bloomLevel: {
      type: DataTypes.INTEGER,
      allowNull: true,
      defaultValue: 1,
      field: "bloom_level",
    },
    languageBarrierRisk: {
      type: DataTypes.FLOAT,
      allowNull: true,
      defaultValue: 0.2,
      field: "language_barrier_risk",
    },
    activeAgents: {
      type: DataTypes.ARRAY(DataTypes.STRING),
      allowNull: true,
      defaultValue: ["academic"],
      field: "active_agents",
    },
  },
  {
    tableName: "initial_profiles",
    timestamps: true,
  },
);

export default InitialProfile;

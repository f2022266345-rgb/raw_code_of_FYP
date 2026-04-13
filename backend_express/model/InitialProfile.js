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
  },
  {
    tableName: "initial_profiles",
    timestamps: true,
  },
);

export default InitialProfile;

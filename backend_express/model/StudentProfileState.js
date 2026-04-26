import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const StudentProfileState = sequelize.define(
  "StudentProfileState",
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    stateId: {
      type: DataTypes.UUID,
      allowNull: false,
      unique: true,
      defaultValue: DataTypes.UUIDV4,
      field: "state_id",
    },
    userId: {
      type: DataTypes.UUID,
      allowNull: false,
      unique: true,
      field: "user_id",
    },
    masterySummary: {
      type: DataTypes.JSONB,
      allowNull: false,
      defaultValue: {},
      field: "mastery_summary",
    },
    accuracyTrendSlope: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "accuracy_trend_slope",
    },
    timeTrendSlope: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "time_trend_slope",
    },
    hintTrendSlope: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "hint_trend_slope",
    },
    frustrationEstimate: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "frustration_estimate",
    },
    engagementEstimate: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "engagement_estimate",
    },
    readinessEstimate: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "readiness_estimate",
    },
    hiddenState: {
      type: DataTypes.JSONB,
      allowNull: false,
      defaultValue: {},
      field: "hidden_state",
    },
    interactionWindow: {
      type: DataTypes.INTEGER,
      allowNull: false,
      defaultValue: 8,
      field: "interaction_window",
    },
    lastComputedAt: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
      field: "last_computed_at",
    },
  },
  {
    tableName: "student_profile_state",
    timestamps: true,
  },
);

export default StudentProfileState;

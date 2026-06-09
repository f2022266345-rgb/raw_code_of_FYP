import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const StudentInteraction = sequelize.define(
  "StudentInteraction",
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    interactionId: {
      type: DataTypes.UUID,
      allowNull: false,
      unique: true,
      defaultValue: DataTypes.UUIDV4,
      field: "interaction_id",
    },
    userId: {
      type: DataTypes.UUID,
      allowNull: false,
      field: "user_id",
    },
    sessionId: {
      type: DataTypes.STRING,
      allowNull: true,
      field: "session_id",
    },
    eventType: {
      type: DataTypes.STRING,
      allowNull: false,
      field: "event_type",
    },
    contentId: {
      type: DataTypes.STRING,
      allowNull: true,
      field: "content_id",
    },
    agentType: {
      type: DataTypes.STRING,
      allowNull: true,
      field: "agent_type",
    },
    correctness: {
      type: DataTypes.BOOLEAN,
      allowNull: true,
      field: "correctness",
    },
    hintsRequested: {
      type: DataTypes.INTEGER,
      allowNull: true,
      field: "hints_requested",
    },
    attempts: {
      type: DataTypes.INTEGER,
      allowNull: true,
      field: "attempts",
    },
    responseTimeMs: {
      type: DataTypes.INTEGER,
      allowNull: true,
      field: "response_time_ms",
    },
    sessionTimeSpentMs: {
      type: DataTypes.INTEGER,
      allowNull: true,
      field: "session_time_spent_ms",
    },
    messageText: {
      type: DataTypes.TEXT,
      allowNull: true,
      field: "message_text",
    },
    sentimentScore: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "sentiment_score",
    },
    sentimentLabel: {
      type: DataTypes.STRING,
      allowNull: true,
      field: "sentiment_label",
    },
    metadata: {
      type: DataTypes.JSONB,
      allowNull: true,
      field: "metadata",
    },
    occurredAt: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
      field: "occurred_at",
    },
  },
  {
    tableName: "student_interactions",
    timestamps: true,
  },
);

export default StudentInteraction;

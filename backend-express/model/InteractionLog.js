import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const InteractionLog = sequelize.define(
  "InteractionLog",
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    eventId: {
      type: DataTypes.UUID,
      defaultValue: DataTypes.UUIDV4,
      allowNull: false,
      unique: true,
      field: "event_id",
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
    pagePath: {
      type: DataTypes.STRING,
      allowNull: true,
      field: "page_path",
    },
    correct: {
      type: DataTypes.BOOLEAN,
      allowNull: true,
    },
    responseTimeMs: {
      type: DataTypes.INTEGER,
      allowNull: true,
      field: "response_time_ms",
    },
    hintsUsed: {
      type: DataTypes.INTEGER,
      allowNull: true,
      field: "hints_used",
    },
    attempts: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
    timeOnPageMs: {
      type: DataTypes.INTEGER,
      allowNull: true,
      field: "time_on_page_ms",
    },
    clickCount: {
      type: DataTypes.INTEGER,
      allowNull: true,
      field: "click_count",
    },
    mood: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    confidenceScore: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "confidence_score",
    },
    chatText: {
      type: DataTypes.TEXT,
      allowNull: true,
      field: "chat_text",
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
    },
    occurredAt: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
      field: "occurred_at",
    },
  },
  {
    tableName: "interaction_logs",
    timestamps: true,
  },
);

export default InteractionLog;
import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const WellnessLog = sequelize.define(
  "WellnessLog",
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

    // ── Wellness classification ─────────────────────────────────────
    sentimentMarker: {
      type: DataTypes.STRING(80),
      allowNull: false,
      defaultValue: "Neutral",
      field: "sentiment_marker",  // 'Stressed' | 'Low' | 'Stable' | 'Neutral'
    },
    stressIndicator: {
      type: DataTypes.FLOAT,
      allowNull: true,
      defaultValue: 0.0,
      field: "stress_indicator",   // 0.0 – 1.0
      validate: { min: 0, max: 1 },
    },
    familyPressure: {
      type: DataTypes.BOOLEAN,
      allowNull: true,
      defaultValue: false,
      field: "family_pressure",
    },

    // ── Source and context ─────────────────────────────────────────
    source: {
      type: DataTypes.STRING(50),
      allowNull: true,
      defaultValue: "chat",
      field: "source",  // 'onboarding' | 'chat' | 'observation'
    },
    nearestClinicId: {
      type: DataTypes.STRING(120),
      allowNull: true,
      field: "nearest_clinic_id",
    },
    loggedAt: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
      field: "logged_at",
    },
  },
  {
    timestamps: false,
    tableName: "wellness_logs",
  },
);

export default WellnessLog;

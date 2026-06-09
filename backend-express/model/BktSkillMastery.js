import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

/**
 * BktSkillMastery — per-user BKT knowledge state for each skill.
 *
 * Seeded at onboarding time with p_init from the trained CSV.
 * Updated in real-time as the student answers questions using the BKT formula.
 */
const BktSkillMastery = sequelize.define(
  "BktSkillMastery",
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    userId: {
      type: DataTypes.UUID,
      allowNull: false,
      field: "user_id",
    },
    skillName: {
      type: DataTypes.STRING(200),
      allowNull: false,
      field: "skill_name",
    },
    category: {
      type: DataTypes.STRING(100),
      allowNull: true,
      defaultValue: "General",
    },
    // Current estimated mastery probability [0, 1]
    pMastery: {
      type: DataTypes.FLOAT,
      allowNull: false,
      defaultValue: 0.3,
      field: "p_mastery",
    },
    // BKT Parameters (from trained CSV)
    pInit: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "p_init",
    },
    pTransit: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "p_transit",
    },
    pGuess: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "p_guess",
    },
    pSlip: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "p_slip",
    },
    pForget: {
      type: DataTypes.FLOAT,
      allowNull: true,
      field: "p_forget",
    },
    // How many times has this skill been practiced
    practiceCount: {
      type: DataTypes.INTEGER,
      allowNull: false,
      defaultValue: 0,
      field: "practice_count",
    },
    lastPracticedAt: {
      type: DataTypes.DATE,
      allowNull: true,
      field: "last_practiced_at",
    },
  },
  {
    tableName: "bkt_skill_mastery",
    timestamps: true,
    indexes: [
      {
        unique: true,
        fields: ["user_id", "skill_name"],
        name: "bkt_user_skill_unique",
      },
      {
        fields: ["user_id"],
        name: "bkt_user_idx",
      },
    ],
  },
);

export default BktSkillMastery;

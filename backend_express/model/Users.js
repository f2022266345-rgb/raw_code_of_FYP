import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js"; // Ensure the curly braces match your export

const User = sequelize.define(
  "User",
  {
    // 1. Auto-incrementing internal ID
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    // 2. Public User ID (good for URLs/API responses)
    userId: {
      type: DataTypes.UUID,
      defaultValue: DataTypes.UUIDV4,
      allowNull: false,
      unique: true,
    },
    // 3. Persistent Learner ID (from ML backend, stable across sessions)
    persistentLearnerId: {
      type: DataTypes.UUID,
      allowNull: true,
      unique: true,
      field: "persistent_learner_id",
    },
    name: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    email: {
      type: DataTypes.STRING,
      allowNull: false,
      unique: true,
      validate: {
        isEmail: true,
      },
    },
    password: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    // Adding this since your frontend logic checks for onboarding status
    isOnboarded: {
      type: DataTypes.BOOLEAN,
      defaultValue: false,
    },
  },
  {
    // Timestamps add 'createdAt' and 'updatedAt' automatically
    timestamps: true,
    tableName: "users", // Explicitly naming the table in the DB
  },
);

export default User;

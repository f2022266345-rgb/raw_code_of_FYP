import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const AcademicProgress = sequelize.define(
  "AcademicProgress",
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
    courseName: {
      type: DataTypes.STRING(200),
      allowNull: false,
      field: "course_name",
    },
    currentBloomLevel: {
      type: DataTypes.INTEGER,
      allowNull: false,
      defaultValue: 1,
      field: "current_bloom_level",
      validate: { min: 1, max: 6 },
    },
    completedTopics: {
      type: DataTypes.ARRAY(DataTypes.TEXT),
      allowNull: false,
      defaultValue: [],
      field: "completed_topics",
    },
    lastAssessed: {
      type: DataTypes.DATE,
      allowNull: true,
      field: "last_assessed",
    },
  },
  {
    timestamps: false,
    tableName: "academic_progress",
    indexes: [
      {
        unique: true,
        fields: ["user_id", "course_name"],
        name: "academic_progress_user_course_unique",
      },
    ],
  },
);

export default AcademicProgress;

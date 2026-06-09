import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const ChatThread = sequelize.define(
  "ChatThread",
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
    currentRoutingAgent: {
      type: DataTypes.STRING(40),
      allowNull: false,
      defaultValue: "coordinator",
      field: "current_routing_agent",
    },
    createdAt: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
      field: "created_at",
    },
  },
  {
    timestamps: false,
    tableName: "chat_threads",
  },
);

export default ChatThread;

import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const VALID_SENDERS = [
  "user",
  "coordinator",
  "academic",
  "social",
  "wellness",
];

const ChatMessage = sequelize.define(
  "ChatMessage",
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
      allowNull: false,
    },
    threadId: {
      type: DataTypes.UUID,
      allowNull: false,
      field: "thread_id",
      references: { model: "chat_threads", key: "id" },
      onDelete: "CASCADE",
    },
    sender: {
      type: DataTypes.STRING(40),
      allowNull: false,
      validate: {
        isIn: [VALID_SENDERS],
      },
    },
    messageText: {
      type: DataTypes.TEXT,
      allowNull: false,
      field: "message_text",
    },
    uiCardMetadata: {
      type: DataTypes.JSONB,
      allowNull: true,
      defaultValue: null,
      field: "ui_card_metadata",
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
    tableName: "chat_messages",
  },
);

export { VALID_SENDERS };
export default ChatMessage;

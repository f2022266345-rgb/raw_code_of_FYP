import { DataTypes } from "sequelize";
import { sequelize } from "../config/database.js";

const User = sequelize.define(
  "User",
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
      allowNull: false,
    },
    clerkId: {
      type: DataTypes.STRING(255),
      allowNull: false,
      unique: true,
      field: "clerk_id",
    },
    email: {
      type: DataTypes.STRING(255),
      allowNull: false,
      unique: true,
      validate: { isEmail: true },
    },
    fullName: {
      type: DataTypes.STRING(255),
      allowNull: false,
      field: "full_name",
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
    tableName: "users",
  },
);

export default User;

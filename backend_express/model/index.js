import { sequelize } from "../config/database.js";
import User from "./Users.js"; // Import the User model
import InitialProfile from "./InitialProfile.js";
import InteractionLog from "./InteractionLog.js";

// Initialize models and associations here if needed
// For example, if you have other models like Post, Comment, etc., you can define associations here
// Add other models here if needed

const db = {
  User,
  InitialProfile,
  InteractionLog,
  sequelize,
};

User.hasOne(InitialProfile, {
  foreignKey: "userId",
  sourceKey: "userId",
  as: "initialProfile",
  onDelete: "CASCADE",
});

InitialProfile.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "userId",
  as: "user",
});

User.hasMany(InteractionLog, {
  foreignKey: "userId",
  sourceKey: "userId",
  as: "interactionLogs",
  onDelete: "CASCADE",
});

InteractionLog.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "userId",
  as: "user",
});

export default db;
export { sequelize };

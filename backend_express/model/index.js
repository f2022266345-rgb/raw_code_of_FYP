import { sequelize } from "../config/database.js";
import User from "./Users.js"; // Import the User model
import InitialProfile from "./InitialProfile.js";
import InteractionLog from "./InteractionLog.js";
import BktSkillMastery from "./BktSkillMastery.js";
import StudentInteraction from "./StudentInteraction.js";
import StudentProfileState from "./StudentProfileState.js";

// Initialize models and associations here if needed
// For example, if you have other models like Post, Comment, etc., you can define associations here
// Add other models here if needed

const db = {
  User,
  InitialProfile,
  InteractionLog,
  BktSkillMastery,
  StudentInteraction,
  StudentProfileState,
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

User.hasMany(StudentInteraction, {
  foreignKey: "userId",
  sourceKey: "userId",
  as: "studentInteractions",
  onDelete: "CASCADE",
});

StudentInteraction.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "userId",
  as: "user",
});

User.hasOne(StudentProfileState, {
  foreignKey: "userId",
  sourceKey: "userId",
  as: "profileState",
  onDelete: "CASCADE",
});

StudentProfileState.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "userId",
  as: "user",
});

// BKT Skill Mastery associations
User.hasMany(BktSkillMastery, {
  foreignKey: "userId",
  sourceKey: "userId",
  as: "bktSkills",
  onDelete: "CASCADE",
});

BktSkillMastery.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "userId",
  as: "user",
});

export default db;
export { sequelize };

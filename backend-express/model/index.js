import { sequelize } from "../config/database.js";
import User from "./Users.js";
import DiagnosticProfile from "./DiagnosticProfile.js";
import InitialProfile from "./InitialProfile.js";
import AcademicProgress from "./AcademicProgress.js";
import SocialMetrics from "./SocialMetrics.js";
import WellnessLog from "./WellnessLog.js";
import ChatThread from "./ChatThread.js";
import ChatMessage from "./ChatMessage.js";
import CounselorCase from "./CounselorCase.js";
import BktSkillMastery from "./BktSkillMastery.js";
import StudentProfileState from "./StudentProfileState.js";
import InteractionLog from "./InteractionLog.js";

const db = {
  User,
  DiagnosticProfile,
  InitialProfile,
  AcademicProgress,
  SocialMetrics,
  WellnessLog,
  ChatThread,
  ChatMessage,
  CounselorCase,
  BktSkillMastery,
  StudentProfileState,
  InteractionLog,
  sequelize,
};

// ── User → DiagnosticProfile (one-to-one) ──────────────────────────
User.hasOne(DiagnosticProfile, {
  foreignKey: "userId",
  sourceKey: "id",
  as: "diagnosticProfile",
  onDelete: "CASCADE",
});
DiagnosticProfile.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "id",
  as: "user",
});

// ── User → InitialProfile (one-to-one) ────────────────────────────
User.hasOne(InitialProfile, {
  foreignKey: "userId",
  sourceKey: "id",
  as: "initialProfile",
  onDelete: "CASCADE",
});
InitialProfile.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "id",
  as: "user",
});

// ── User → AcademicProgress (one-to-many) ─────────────────────────
User.hasMany(AcademicProgress, {
  foreignKey: "userId",
  sourceKey: "id",
  as: "academicProgress",
  onDelete: "CASCADE",
});
AcademicProgress.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "id",
  as: "user",
});

// ── User → SocialMetrics (one-to-one) ─────────────────────────────
User.hasOne(SocialMetrics, {
  foreignKey: "userId",
  sourceKey: "id",
  as: "socialMetrics",
  onDelete: "CASCADE",
});
SocialMetrics.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "id",
  as: "user",
});

// ── User → WellnessLog (one-to-many) ──────────────────────────────
User.hasMany(WellnessLog, {
  foreignKey: "userId",
  sourceKey: "id",
  as: "wellnessLogs",
  onDelete: "CASCADE",
});
WellnessLog.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "id",
  as: "user",
});

// ── User → ChatThread (one-to-many) ──────────────────────────────
User.hasMany(ChatThread, {
  foreignKey: "userId",
  sourceKey: "id",
  as: "chatThreads",
  onDelete: "CASCADE",
});
ChatThread.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "id",
  as: "user",
});

// ── ChatThread → ChatMessage (one-to-many) ────────────────────────
ChatThread.hasMany(ChatMessage, {
  foreignKey: "threadId",
  sourceKey: "id",
  as: "messages",
  onDelete: "CASCADE",
});
ChatMessage.belongsTo(ChatThread, {
  foreignKey: "threadId",
  targetKey: "id",
  as: "thread",
});

// ── User → CounselorCase (one-to-many) ───────────────────────────
User.hasMany(CounselorCase, {
  foreignKey: "userId",
  sourceKey: "id",
  as: "counselorCases",
  onDelete: "CASCADE",
});
CounselorCase.belongsTo(User, {
  foreignKey: "userId",
  targetKey: "id",
  as: "student",
});

export default db;
export { sequelize };

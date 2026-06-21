// services/profileMapper.js
// Maps raw onboarding form data to structured DB fields for each table.

const SCHOOL_TO_PRIOR_EDUCATION = {
  "public": "FSc",
  "private-english": "O-Level",
  "private-urdu": "FSc",
  "military": "FSc",
  "religious": "FSc",
  "international": "A-Level",
  other: "Other",
};

const LANGUAGE_LABELS = {
  urdu: "Urdu",
  punjabi: "Punjabi",
  sindhi: "Sindhi",
  pashto: "Pashto",
  balochi: "Balochi",
  english: "English",
  mixed: "Mixed",
  other: "Other",
};

const AI_TO_TECH_ACCESS = {
  never: "Mobile Only",
  chatgpt: "Laptop",
  "educational-apps": "Laptop",
  "tutoring-systems": "Laptop",
  "very-experienced": "Laptop + Mobile",
};

// Wellness-linked challenge keywords
const STRESS_CHALLENGES = [
  "financial-pressure", "family-responsibilities", "health-issues",
  "transportation", "mental-health", "no-support", "language-barrier",
];
const MODERATE_STRESS_CHALLENGES = [
  "lack-of-resources", "time-management", "peer-pressure",
  "academic-pressure", "gender-barriers",
];

// ─────────────────────────────────────────────────────────────────────
// Map onboarding form → DiagnosticProfile fields
// ─────────────────────────────────────────────────────────────────────
export const mapToDiagnosticProfile = ({
  educationalBackground = {},
  learningPreferences = {},
  culturalContext = {},
  diagnosticAssessment = {},
  explicit = {},
}) => {
  const priorEducation =
    explicit.priorEducation ||
    SCHOOL_TO_PRIOR_EDUCATION[educationalBackground.schoolType] ||
    educationalBackground.program ||
    "FSc";

  const primaryLanguage =
    explicit.primaryLanguage ||
    LANGUAGE_LABELS[culturalContext.primaryLanguage] ||
    "Urdu";

  const commuteType =
    explicit.commuteType ||
    (culturalContext.background === "rural" ? "Day Scholar" : "Hostelite");

  const techAccess =
    explicit.techAccess ||
    AI_TO_TECH_ACCESS[learningPreferences.aiExperience] ||
    "Laptop";

  // Derive bloom level from self-assessment data (FastAPI ML will refine further)
  const confidenceLevel = Number(diagnosticAssessment.confidenceLevel || 5);
  const currentSemester = Number(diagnosticAssessment.currentSemester || 1);
  const previousPerformance = diagnosticAssessment.previousPerformance || "average";
  const performanceBonus =
    previousPerformance === "excellent" ? 2 :
    previousPerformance === "good" ? 1 :
    previousPerformance === "below-average" ? -1 : 0;
  const semesterBonus = currentSemester >= 5 ? 1 : 0;
  const derivedBloom = Math.min(6, Math.max(1,
    Math.round((confidenceLevel / 10) * 4 + performanceBonus + semesterBonus)
  ));

  const bloomLevel = Number(
    diagnosticAssessment.bloomLevel ||
    diagnosticAssessment.bloom_level ||
    derivedBloom,
  );

  // Courses to seed in academic_progress
  const courses = [
    educationalBackground.program,
    learningPreferences.strongestSubject,
    learningPreferences.weakestSubject,
  ]
    .filter(Boolean)
    .map((name) => String(name).trim());
  const uniqueCourses = [...new Set(courses)].slice(0, 4);

  return {
    // DiagnosticProfile flat columns
    university: educationalBackground.university || null,
    program: educationalBackground.program || null,
    priorEducation: String(priorEducation).slice(0, 120),
    schoolType: educationalBackground.schoolType || null,
    primaryLanguage: String(primaryLanguage).slice(0, 80),
    englishProficiency: educationalBackground.englishProficiency || null,
    yearsEnglish: educationalBackground.yearsEnglish || null,
    previousMedium: educationalBackground.previousMedium || [],
    studyPace: learningPreferences.studyPace || null,
    languagePreference: learningPreferences.languagePreference || null,
    studyHabits: learningPreferences.studyHabits || null,
    studyHoursPerWeek: learningPreferences.studyHoursPerWeek || null,
    learningStyles: learningPreferences.learningStyles || {},
    commuteType: String(commuteType).slice(0, 80),
    techAccess: String(techAccess).slice(0, 80),
    // Helpers
    bloomLevel: Math.min(6, Math.max(1, bloomLevel || 1)),
    courses: uniqueCourses.length > 0 ? uniqueCourses : ["General Studies"],
  };
};

// Backward-compat alias used by existing callers
export const mapOnboardingToDiagnosticProfile = mapToDiagnosticProfile;

// ─────────────────────────────────────────────────────────────────────
// Map cultural context → SocialMetrics fields
// ─────────────────────────────────────────────────────────────────────
export const mapToSocialMetrics = ({ culturalContext = {} }) => {
  const challenges = culturalContext.challenges || [];
  const familySupport = culturalContext.familySupport || "moderate";

  // Communication score: start at 60, adjust by family support and challenges
  let communicationScore = 60;
  if (familySupport === "very-strong") communicationScore += 15;
  if (familySupport === "limited") communicationScore -= 15;
  if (culturalContext.firstGenStudent) communicationScore -= 5;
  if (challenges.includes("language-barrier")) communicationScore -= 10;
  communicationScore = Math.min(100, Math.max(0, communicationScore));

  return {
    firstGenStudent: Boolean(culturalContext.firstGenStudent),
    familySupport: familySupport,
    city: culturalContext.city || null,
    background: culturalContext.background || null,
    challenges: challenges,
    learningContext: culturalContext.learningContext || [],
    communicationScore,
  };
};

// ─────────────────────────────────────────────────────────────────────
// Map cultural context → initial WellnessLog entry
// ─────────────────────────────────────────────────────────────────────
export const mapToInitialWellness = ({ culturalContext = {} }) => {
  const challenges = culturalContext.challenges || [];
  const familySupport = culturalContext.familySupport || "moderate";

  // Compute stress indicator 0.0–1.0
  let stressCount = 0;
  for (const c of challenges) {
    if (STRESS_CHALLENGES.includes(c)) stressCount += 2;
    else if (MODERATE_STRESS_CHALLENGES.includes(c)) stressCount += 1;
  }
  const stressIndicator = Math.min(1.0, stressCount / 6);

  // Sentiment marker
  let sentimentMarker = "Neutral";
  if (stressIndicator >= 0.6) sentimentMarker = "Stressed";
  else if (stressIndicator >= 0.35) sentimentMarker = "Low";
  else if (familySupport === "very-strong" && stressIndicator < 0.2) sentimentMarker = "Stable";

  const familyPressure =
    challenges.includes("family-responsibilities") ||
    familySupport === "limited";

  return {
    sentimentMarker,
    stressIndicator: parseFloat(stressIndicator.toFixed(2)),
    familyPressure,
    source: "onboarding",
  };
};

// ─────────────────────────────────────────────────────────────────────
// Derive cognitive rules from onboarding data (used by AI agents)
// ─────────────────────────────────────────────────────────────────────
export const deriveCognitiveRules = ({
  educationalBackground = {},
  learningPreferences = {},
  culturalContext = {},
}) => {
  const languagePreference = learningPreferences.languagePreference || "english-urdu-terms";
  const studyPace = learningPreferences.studyPace || "moderate";
  const englishProficiency = educationalBackground.englishProficiency || "intermediate";

  const needsLanguageSupport =
    languagePreference !== "english-only" ||
    ["beginner", "elementary"].includes(englishProficiency);

  const pacing =
    studyPace === "slow" ? "extended" :
    studyPace === "fast" ? "accelerated" : "standard";

  const chunking =
    learningPreferences.studyHabits === "cramper" ? "micro" : "standard";

  return {
    pacing,
    chunking,
    languageSupport: needsLanguageSupport,
    languagePreference,
    firstGenSupport: Boolean(culturalContext.firstGenStudent),
  };
};

// ─────────────────────────────────────────────────────────────────────
// Determine which agents should be active based on support flags
// ─────────────────────────────────────────────────────────────────────
export const deriveActiveAgents = ({
  wellnessSupportNeeded = false,
  socialSupportNeeded = false,
  academicSupportNeeded = true,
}) => {
  const agents = ["academic"]; // always active
  if (wellnessSupportNeeded) agents.push("wellness");
  if (socialSupportNeeded) agents.push("social");
  return agents;
};

// ─────────────────────────────────────────────────────────────────────
// Sentiment mapper (used by chat/observation pipeline)
// ─────────────────────────────────────────────────────────────────────
export const mapSentimentToWellnessMarker = (text = "") => {
  const lower = String(text).toLowerCase();
  if (/(stress|anxious|panic|overwhelm)/.test(lower)) return "Stressed";
  if (/(sad|depress|lonely)/.test(lower)) return "Low";
  if (/(happy|calm|good|great)/.test(lower)) return "Stable";
  return "Neutral";
};

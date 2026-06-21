-- ============================================================
-- LUMINA DIGITAL TWIN TABLES
-- Migration 002 - Run after 001_lumina_core_schema.sql
-- Target database: see backend-express/.env DATABASE_URL
-- ============================================================

-- Extensions (safe to re-run)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- LAYER 1: STUDENT PROFILES (supplements existing users table)
-- ============================================================

CREATE TABLE IF NOT EXISTS student_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,

    education_level VARCHAR(50),
    university VARCHAR(255),
    major VARCHAR(255),
    entrance_exam_score FLOAT,

    first_language VARCHAR(100),
    english_proficiency VARCHAR(50),
    language_barrier_risk FLOAT DEFAULT 0.5,

    cultural_background JSONB,
    socioeconomic_status VARCHAR(50),
    first_generation_student BOOLEAN,

    learning_style VARCHAR(50),
    preferred_challenge_level VARCHAR(50),
    study_location JSONB,

    academic_support_needed BOOLEAN DEFAULT FALSE,
    wellness_support_needed BOOLEAN DEFAULT FALSE,
    social_support_needed BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_student_profiles_user ON student_profiles(user_id);

-- ============================================================
-- LAYER 2: COGNITIVE STATE MODEL
-- ============================================================

CREATE TABLE IF NOT EXISTS cognitive_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,

    current_bloom_level INT DEFAULT 1 CHECK (current_bloom_level BETWEEN 1 AND 6),
    bkt_mastery_snapshot JSONB,
    cognitive_state VARCHAR(50) DEFAULT 'developing',
    state_confidence FLOAT DEFAULT 0.5,

    engagement_level VARCHAR(50) DEFAULT 'engaged',
    frustration_estimate FLOAT DEFAULT 0.3,
    motivation_index FLOAT DEFAULT 0.7,
    cognitive_load_estimate FLOAT DEFAULT 0.4,

    learning_velocity FLOAT DEFAULT 0.0,
    avg_time_per_problem FLOAT,
    session_duration_preference INT,

    last_updated TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cognitive_state_user ON cognitive_state(user_id);
CREATE INDEX IF NOT EXISTS idx_cognitive_state_bloom ON cognitive_state(current_bloom_level);
CREATE INDEX IF NOT EXISTS idx_cognitive_state_engagement ON cognitive_state(engagement_level);

-- ============================================================
-- LAYER 3: TEMPORAL LEARNING DATA
-- ============================================================

CREATE TABLE IF NOT EXISTS learning_interactions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID,

    interaction_type VARCHAR(50),
    problem_id INT,
    skill_id INT,

    correct BOOLEAN,
    time_on_task_ms INT,
    attempt_count INT,
    hints_used INT,
    confidence_before FLOAT,
    confidence_after FLOAT,

    mood VARCHAR(50),
    stress_level INT,

    interaction_timestamp TIMESTAMPTZ DEFAULT NOW(),
    device_type VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_li_user_time ON learning_interactions(user_id, interaction_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_li_skill ON learning_interactions(skill_id);
CREATE INDEX IF NOT EXISTS idx_li_session ON learning_interactions(session_id);

-- ============================================================
-- LAYER 5: SKILL MASTERY (Digital Twin - uses integer skill_id)
-- NOTE: Different from bkt_skill_mastery which uses skill_name
-- ============================================================

CREATE TABLE IF NOT EXISTS skill_mastery (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    skill_id INT,

    p_mastery FLOAT DEFAULT 0.2,
    p_init FLOAT DEFAULT 0.2,
    p_transit FLOAT DEFAULT 0.1,
    p_guess FLOAT DEFAULT 0.25,
    p_slip FLOAT DEFAULT 0.05,

    correct_count INT DEFAULT 0,
    incorrect_count INT DEFAULT 0,
    practice_count INT DEFAULT 0,

    last_practiced TIMESTAMPTZ,
    days_since_practice INT,

    UNIQUE(user_id, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_skill_mastery_user ON skill_mastery(user_id);
CREATE INDEX IF NOT EXISTS idx_skill_mastery_p ON skill_mastery(user_id, p_mastery DESC);

-- ============================================================
-- LAYER 6: AFFECTIVE & WELLNESS STATE
-- ============================================================

CREATE TABLE IF NOT EXISTS wellness_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,

    stress_level_30d FLOAT DEFAULT 0.3,
    anxiety_markers TEXT[] DEFAULT '{}',
    burnout_risk FLOAT DEFAULT 0.0,

    has_study_group BOOLEAN DEFAULT FALSE,
    peer_interaction_frequency VARCHAR(50),
    social_integration_score FLOAT DEFAULT 0.5,

    family_pressure_level INT DEFAULT 2,
    home_study_environment_quality VARCHAR(50) DEFAULT 'moderate',

    last_wellness_check TIMESTAMPTZ,
    recommended_intervention VARCHAR(255),
    intervention_status VARCHAR(50) DEFAULT 'pending',

    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wellness_state_stress ON wellness_state(stress_level_30d DESC);
CREATE INDEX IF NOT EXISTS idx_wellness_state_user ON wellness_state(user_id);

-- ============================================================
-- LAYER 7: DIGITAL TWIN PREDICTIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS digital_twin_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,

    predicted_next_problem_correctness FLOAT DEFAULT 0.5,
    predicted_learning_trajectory JSONB,

    at_risk_probability FLOAT DEFAULT 0.3,
    intervention_urgency VARCHAR(50) DEFAULT 'normal',

    recommended_agent_type VARCHAR(50) DEFAULT 'coordinator',
    recommended_pacing VARCHAR(50),
    recommended_learning_style_adjustment VARCHAR(255),

    prediction_timestamp TIMESTAMPTZ DEFAULT NOW(),
    confidence_score FLOAT DEFAULT 0.5,
    model_version VARCHAR(50) DEFAULT 'baseline'
);

CREATE INDEX IF NOT EXISTS idx_dt_predictions_risk ON digital_twin_predictions(at_risk_probability DESC);
CREATE INDEX IF NOT EXISTS idx_dt_predictions_user ON digital_twin_predictions(user_id);

-- ============================================================
-- LAYER 10: LEARNING PROGRESS & MILESTONES
-- ============================================================

CREATE TABLE IF NOT EXISTS learning_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,

    current_topic VARCHAR(255),
    topic_start_date TIMESTAMPTZ,

    problems_completed INT DEFAULT 0,
    problems_correct INT DEFAULT 0,
    estimated_completion_date TIMESTAMPTZ,

    milestones_achieved TEXT[] DEFAULT '{}',
    next_milestone VARCHAR(255),

    pacing_adjustments JSONB,
    language_support_level VARCHAR(50) DEFAULT 'none',
    chunking_size VARCHAR(50) DEFAULT 'medium',

    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_learning_progress_user ON learning_progress(user_id);

-- ============================================================
-- DIGITAL TWIN SUMMARY VIEW
-- ============================================================

DROP VIEW IF EXISTS student_digital_twin CASCADE;
CREATE VIEW student_digital_twin AS
SELECT
    u.id,
    u.email,
    sp.major,
    sp.language_barrier_risk,
    cs.current_bloom_level,
    cs.cognitive_state,
    cs.engagement_level,
    cs.frustration_estimate,
    cs.motivation_index,
    (SELECT AVG(p_mastery) FROM skill_mastery WHERE user_id = u.id) AS avg_mastery,
    COUNT(DISTINCT li.id) AS total_interactions,
    ws.stress_level_30d,
    dtp.at_risk_probability,
    dtp.recommended_agent_type
FROM users u
LEFT JOIN student_profiles sp ON u.id = sp.user_id
LEFT JOIN cognitive_state cs ON u.id = cs.user_id
LEFT JOIN learning_interactions li ON u.id = li.user_id
LEFT JOIN wellness_state ws ON u.id = ws.user_id
LEFT JOIN digital_twin_predictions dtp ON u.id = dtp.user_id
GROUP BY
    u.id, u.email, sp.major, sp.language_barrier_risk,
    cs.current_bloom_level, cs.cognitive_state,
    cs.engagement_level, cs.frustration_estimate, cs.motivation_index,
    ws.stress_level_30d, dtp.at_risk_probability, dtp.recommended_agent_type;

-- ============================================================
-- VERIFY
-- ============================================================
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
      'student_profiles', 'cognitive_state', 'learning_interactions',
      'skill_mastery', 'wellness_state', 'digital_twin_predictions',
      'learning_progress'
  )
ORDER BY tablename;

-- Lumina core schema (7 tables) + dev local-auth bridge
-- Target database: FYP_backup (see backend_express/.env DATABASE_URL)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Drop legacy Lumina tables if re-running on a dev database
DROP TABLE IF EXISTS chat_messages CASCADE;
DROP TABLE IF EXISTS chat_threads CASCADE;
DROP TABLE IF EXISTS wellness_logs CASCADE;
DROP TABLE IF EXISTS social_metrics CASCADE;
DROP TABLE IF EXISTS academic_progress CASCADE;
DROP TABLE IF EXISTS diagnostic_profiles CASCADE;
DROP TABLE IF EXISTS user_local_credentials CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Legacy tables from previous architecture (optional cleanup)
DROP TABLE IF EXISTS interaction_logs CASCADE;
DROP TABLE IF EXISTS student_interactions CASCADE;
DROP TABLE IF EXISTS student_profile_state CASCADE;
DROP TABLE IF EXISTS bkt_skill_mastery CASCADE;
DROP TABLE IF EXISTS initial_profiles CASCADE;

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_id VARCHAR(255) NOT NULL UNIQUE,
  email VARCHAR(255) NOT NULL UNIQUE,
  full_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE diagnostic_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  prior_education VARCHAR(120) NOT NULL,
  primary_language VARCHAR(80) NOT NULL,
  commute_type VARCHAR(80) NOT NULL,
  tech_access VARCHAR(80) NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE academic_progress (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  course_name VARCHAR(200) NOT NULL,
  current_bloom_level INTEGER NOT NULL DEFAULT 1 CHECK (current_bloom_level BETWEEN 1 AND 6),
  completed_topics TEXT[] NOT NULL DEFAULT '{}',
  last_assessed TIMESTAMPTZ,
  CONSTRAINT academic_progress_user_course_unique UNIQUE (user_id, course_name)
);

CREATE TABLE social_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  linkedin_optimized BOOLEAN NOT NULL DEFAULT FALSE,
  instagram_optimized BOOLEAN NOT NULL DEFAULT FALSE,
  communication_score INTEGER NOT NULL DEFAULT 50 CHECK (communication_score BETWEEN 0 AND 100),
  last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE wellness_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  sentiment_marker VARCHAR(80) NOT NULL,
  nearest_clinic_id VARCHAR(120),
  logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE chat_threads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  current_routing_agent VARCHAR(40) NOT NULL DEFAULT 'coordinator',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX chat_threads_user_id_idx ON chat_threads(user_id);

CREATE TABLE chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
  sender VARCHAR(40) NOT NULL CHECK (sender IN ('user', 'coordinator', 'academic', 'social', 'wellness')),
  message_text TEXT NOT NULL,
  ui_card_metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX chat_messages_thread_id_idx ON chat_messages(thread_id);
CREATE INDEX chat_messages_created_at_idx ON chat_messages(created_at DESC);

-- Dev-only bridge for email/password login until Clerk is integrated
CREATE TABLE user_local_credentials (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  password_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

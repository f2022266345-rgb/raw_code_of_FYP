# Lumina Database & Route Audit

**Generated:** 2026-06-07  
**Purpose:** Deep scan of what the codebase actually stores in PostgreSQL, which API routes write/read it, and how that compares to your target 5-table architecture.

---

## Executive Summary

| Your Target Table | Current Equivalent | Status |
|---|---|---|
| `users` (Clerk auth) | `users` (email/password JWT) | **Partial** — same concept, different auth model |
| `diagnostic_profiles` (flat onboarding facts) | `initial_profiles` (JSONB blobs + ML outputs) | **Different shape** — richer, not flat columns |
| `academic_progress` (subject + bloom per row) | `bkt_skill_mastery` + `initial_profiles.bloom_level` | **Different model** — 190 skills via BKT, not subject rows |
| `chat_threads` (LangGraph checkpointer) | In-memory `sessionService` Map + `interaction_logs.session_id` | **Missing** — no persistent thread table |
| `chat_messages` (thread FK, User/AI sender) | `interaction_logs` (`chat_user` / `chat_assistant`) | **Different** — event log, not normalized messages |

**Extra tables in production code (not in your target):**

- `interaction_logs` — observations + chat + page telemetry (catch-all event store)
- `student_interactions` — cognitive/BKT pipeline mirror of observables
- `student_profile_state` — inferred latent state (frustration, readiness, trends)
- `bkt_skill_mastery` — per-skill mastery probabilities
- `agent_memory` — cross-agent mood/cognitive sync (FastAPI-owned)
- `sessions`, `notifications`, `chat_messages` (FastAPI legacy ORM) — **schema exists, active chat flow does not use them**
- `knowledge_chunks` — pgvector RAG corpus (read-only in chat)

---

## Schema Ownership

| Layer | ORM | Tables Created |
|---|---|---|
| **Express (source of truth)** | Sequelize `sequelize.sync({ alter: true })` on boot | `users`, `initial_profiles`, `interaction_logs`, `student_interactions`, `student_profile_state`, `bkt_skill_mastery` |
| **FastAPI (mirror + extras)** | SQLAlchemy `init_db()` on lifespan | `agent_memory`, `sessions`, `notifications`, `chat_messages`, `knowledge_chunks` (+ reads Sequelize tables via ORM mirrors) |

Both backends share one PostgreSQL database (`DATABASE_URL`).

---

## Current Tables (Full Detail)

### 1. `users`

**Model:** `backend_express/model/Users.js`  
**Table name:** `users`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK (auto) | Internal Sequelize PK — **not** your target UUID PK |
| `userId` | UUID (unique) | Public learner ID used everywhere in APIs |
| `persistent_learner_id` | UUID (nullable) | Set after onboarding ML run |
| `name` | STRING | Display name |
| `email` | STRING (unique) | Login identity |
| `password` | STRING (bcrypt) | **No `clerk_id`** — custom JWT auth |
| `isOnboarded` | BOOLEAN | Gates dashboard access |
| `createdAt`, `updatedAt` | TIMESTAMP | Sequelize timestamps |

**Associations:** 1:1 `initial_profiles`, 1:1 `student_profile_state`, 1:N `interaction_logs`, `student_interactions`, `bkt_skill_mastery`

---

### 2. `initial_profiles` (your `diagnostic_profiles` equivalent)

**Model:** `backend_express/model/InitialProfile.js`  
**Table name:** `initial_profiles`

| Column | Type | What goes here |
|---|---|---|
| `profile_id` | UUID | Row identifier |
| `user_id` | UUID FK → `users.userId` | One profile per user |
| `persistent_learner_id` | UUID | Copy from ML response |
| `educational_background` | JSONB | Raw Step 1 form (university, schoolType, englishProficiency, etc.) |
| `learning_preferences` | JSONB | Raw Step 2 (studyPace, VARK styles, languagePreference, etc.) |
| `cultural_context` | JSONB | Raw Step 3 (city, primaryLanguage, familySupport, challenges, etc.) |
| `diagnostic_assessment` | JSONB | Raw Step 4 (bloomLevel, questionResponses, scores) |
| `user_profile` | JSONB | ML-derived learner snapshot (stressLevel, academicConfidence, socialBattery) |
| `ai_prediction` | JSONB | Full ML prediction object |
| `bloom_level_predicted` | INTEGER | ML output |
| `bloom_level` | INTEGER | Active bloom level used in prompts |
| `language_barrier_risk` | FLOAT | ML output |
| `learning_barriers_score` | FLOAT | ML + post-chat LLM updates |
| `wellness_support_needed` | BOOLEAN | ML + post-chat LLM updates |
| `social_support_needed` | BOOLEAN | ML + post-chat LLM updates |
| `academic_support_needed` | BOOLEAN | ML output |
| `cognitive_rules` | JSONB | `{ pacing, chunking, languageSupport }` computed in Express |
| `active_agents` | STRING[] | `["coordinator","academic",...]` |

**vs your target `diagnostic_profiles`:**

| Your column | Current location |
|---|---|
| `prior_education` ("FSc"/"O-Level") | Inside `educational_background` JSON (e.g. `schoolType`, `previousMedium`) — **not a flat column** |
| `primary_language` | Inside `cultural_context.primaryLanguage` |
| `commute_type` | **Not collected** in current onboarding form |
| `tech_access` | **Not collected** as dedicated field |

---

### 3. `bkt_skill_mastery` (partial stand-in for `academic_progress`)

**Model:** `backend_express/model/BktSkillMastery.js`  
**Table name:** `bkt_skill_mastery`

| Column | Type | What goes here |
|---|---|---|
| `user_id` | UUID | Per-user skill rows |
| `skill_name` | STRING(200) | ~190 math skills from BKT CSV |
| `category` | STRING | Algebra, Geometry, etc. |
| `p_mastery` | FLOAT [0,1] | Current BKT probability |
| `p_init`, `p_transit`, `p_guess`, `p_slip`, `p_forget` | FLOAT | Trained BKT parameters |
| `practice_count` | INTEGER | Times practiced |
| `last_practiced_at` | TIMESTAMP | Last BKT update |

**vs your target `academic_progress`:**

| Your column | Current equivalent |
|---|---|
| `subject` | `skill_name` / `category` (skill-granular, not subject-granular) |
| `bloom_level` | Only at profile level (`initial_profiles.bloom_level`), **not per subject row** |
| `last_assessed` | `last_practiced_at` on skill row |

---

### 4. `interaction_logs` (active chat storage — not `chat_messages`)

**Model:** `backend_express/model/InteractionLog.js`  
**Table name:** `interaction_logs`

| Column | Type | What goes here |
|---|---|---|
| `event_id` | UUID | Row ID |
| `user_id` | UUID | Owner |
| `session_id` | STRING (nullable) | JWT session or frontend tracking ID — **not a `chat_threads` FK** |
| `event_type` | STRING | See event types below |
| `page_path` | STRING | e.g. `/dashboard`, `/onboarding` |
| `chat_text` | TEXT | **Chat message body** (user or assistant) |
| `correct`, `response_time_ms`, `hints_used`, `attempts` | various | Learning telemetry |
| `time_on_page_ms`, `click_count` | INTEGER | Engagement telemetry |
| `mood`, `confidence_score` | STRING/FLOAT | Self-reports |
| `sentiment_score`, `sentiment_label` | FLOAT/STRING | Estimated or provided |
| `metadata` | JSONB | Agent, skillName, routing decisions, etc. |
| `occurred_at` | TIMESTAMP | Event time |

**Chat-related `event_type` values:**

- `chat_user` — student message (`chat_text` = message)
- `chat_assistant` — AI reply (`chat_text` = response)

**Other common `event_type` values (from observations):**

- `learning_attempt`, `self_report`, `hint_requested`
- `onboarding_step_next`, `onboarding_step_back`, `onboarding_submit`
- `unknown` (fallback)

**Role mapping (for chat UI):**

| Your `sender` | Current mapping |
|---|---|
| `"User"` | `event_type = 'chat_user'` |
| `"AI"` | `event_type = 'chat_assistant'` |

---

### 5. `student_interactions`

**Model:** `backend_express/model/StudentInteraction.js`  
**Table name:** `student_interactions`

Duplicate/normalized observables layer for cognitive engine. Every observation log and chat log also creates rows here.

| Column | Type | Purpose |
|---|---|---|
| `interaction_id` | UUID | Row ID |
| `user_id` | UUID | Owner |
| `event_type` | STRING | Mirrors interaction_logs types |
| `content_id` | STRING | Skill name / content reference |
| `agent_type` | STRING | academic, wellness, etc. |
| `correctness` | BOOLEAN | For BKT auto-updates |
| `message_text` | TEXT | Chat copy |
| `sentiment_*`, `metadata` | various | Trend computation inputs |

**Downstream:** triggers `recomputeAndStoreProfileState()` → updates `student_profile_state` and auto-updates `bkt_skill_mastery` when `correctness` is set.

---

### 6. `student_profile_state`

**Model:** `backend_express/model/StudentProfileState.js`  
**Table name:** `student_profile_state`

| Column | Type | What goes here |
|---|---|---|
| `user_id` | UUID (unique) | One state row per user |
| `mastery_summary` | JSONB | BKT aggregates (avgMastery, weakSkills) |
| `accuracy_trend_slope`, `time_trend_slope`, `hint_trend_slope` | FLOAT | Regression over last 5–10 interactions |
| `frustration_estimate`, `engagement_estimate`, `readiness_estimate` | FLOAT | Latent state [0,1] |
| `hidden_state` | JSONB | Full latent mapping + trend labels |
| `interaction_window` | INTEGER | Window size used (default 8) |
| `last_computed_at` | TIMESTAMP | Last recompute |

**Not in your target schema** — powers coordinator routing and dashboard hidden-state panel.

---

### 7. `agent_memory` (FastAPI-only)

**Model:** `backend/db.py` → `AgentMemoryORM`  
**Table name:** `agent_memory`

| Column | Type | What goes here |
|---|---|---|
| `user_id` | STRING(36) | User UUID |
| `source_agent` | STRING | wellness \| academic \| coordinator |
| `mood`, `sentiment_label`, `sentiment_score` | various | Emotional sync |
| `cognitive_state` | STRING | FLOW_STATE, CRITICAL_STRUGGLE, etc. |
| `payload` | JSONB | Extra agent data |
| `created_at` | TIMESTAMP | Write time |

**Written by:** `POST /api/agent/wellness/sync` (FastAPI) — **not wired from Express chat today**.

---

### 8. FastAPI Legacy Tables (schema exists, low/no active writes)

#### `sessions`

| Column | Notes |
|---|---|
| `id` | String PK |
| `email`, `name`, `major`, `university` | Profile-ish fields |
| `stress_level`, `academic_confidence`, `social_battery`, `current_mood` | State fields |
| `academic_status`, `social_status`, `wellness_status` | Agent status strings |
| `academic_result`, `social_result`, `wellness_result` | Text results |

**Status:** Defined in `db.py`, created by `init_db()`. **No active route writes to this table** in current Express/FastAPI chat pipeline.

#### `chat_messages` (FastAPI ORM — conflicts with your target name)

| Column | Notes |
|---|---|
| `id` | String PK |
| `session_id` | FK → `sessions.id` (not `thread_id`) |
| `agent_type` | STRING |
| `role` | STRING (not `sender` User/AI) |
| `content` | TEXT |
| `embedding` | VECTOR(256) — **required** pgvector column |

**Status:** Table may exist if `init_db()` ran. **Active chat does NOT write here** — Express writes `interaction_logs` instead.

#### `knowledge_chunks`

| Column | Notes |
|---|---|
| `id`, `agent_type`, `title`, `content` | RAG corpus |
| `embedding` | VECTOR(256) |

**Status:** Read by `gemini_agent.py` for pgvector scaffolding. No route populates it in this repo.

#### `notifications`

**Status:** Legacy relation on `sessions`. Not used by active frontend API calls.

---

## Route → Database Write Map

### Express (`backend_express`) — Port 4000

All routes below require JWT (`Authorization: Bearer`) except auth signup/login.

#### Auth — `/api/auth/*`

| Route | Method | Tables Written | Data Written |
|---|---|---|---|
| `/api/auth/signup` | POST | `users` | `name`, `email`, `password` (hashed), auto `userId` UUID |
| `/api/auth/login` | POST | — (read `users`) | In-memory session via `sessionService` (NOT PostgreSQL) |
| `/api/auth/token` | GET | — (read `users`) | Refreshes in-memory session |
| `/api/auth/logout` | POST | — | Revokes in-memory session |
| `/api/auth/forgot-password` | POST | — (read `users`) | Logs reset token only |

**Session storage:** `backend_express/services/sessionService.js` — **in-memory `Map`**, lost on server restart.

---

#### Onboarding — `/api/initial-profiling`

| Route | Method | Tables Written | Data Written |
|---|---|---|---|
| `/api/initial-profiling` | POST | `initial_profiles` | Step 1: raw JSONB (`educationalBackground`, `learningPreferences`, `culturalContext`, `diagnosticAssessment`) |
| | | `initial_profiles` | Step 3: ML outputs (`userProfile`, `aiPrediction`, bloom/risk/support flags, `cognitiveRules`, `activeAgents`, `persistentLearnerId`) |
| | | `users` | `isOnboarded=true`, `persistentLearnerId` |
| | | `bkt_skill_mastery` | Bulk insert ~190 skills (if none exist for user) |

**FastAPI call (no DB write in Python for onboarding):**

- `POST /api/predict/initial-profile` — inference only, returns JSON to Express

**Frontend caller:** `FYP_Project/app/onboarding/page.tsx`  
**Payload shape:** `{ educationalBackground, learningPreferences, culturalContext, diagnosticAssessment }`

---

#### Chat — `/api/chat/*`

| Route | Method | Tables Written | Data Written |
|---|---|---|---|
| `/api/chat` | POST | `interaction_logs` | User message: `event_type=chat_user`, `chat_text`, `metadata.agent/skillName/routedAgent` |
| | | `student_interactions` | `event_type=chat_message_user`, `message_text`, sentiment estimate |
| | | `student_interactions` | `event_type=coordinator_routing_decision` (JSON decision) |
| | | `interaction_logs` | Assistant reply: `event_type=chat_assistant`, `chat_text`, `metadata.state/persona` |
| | | `student_interactions` | `event_type=chat_message_agent` |
| | | `student_profile_state` | Recomputed via `processNewInteractions()` |
| | | `bkt_skill_mastery` | Auto-updated if interaction has `correctness` |
| `/api/chat/history` | GET | — (read `interaction_logs`) | Filters `chat_user`/`chat_assistant` |
| `/api/chat/memories` | GET | — (read `interaction_logs`) | Groups by topic; calls FastAPI for summaries only |

**FastAPI calls from chat (mostly read + background write):**

| FastAPI Route | DB Effect |
|---|---|
| `POST /api/agent/router` | None |
| `POST /api/agent/chat` | **Read:** `bkt_skill_mastery`, `initial_profiles`, `interaction_logs`, `agent_memory` |
| | **Background write:** `initial_profiles` (`learning_barriers_score`, `wellness_support_needed`, `social_support_needed`) via LLM extraction |
| `POST /api/agent/memory/summary` | None |

**Frontend callers:** `agent-chat.tsx`, `chat-widget.tsx`, `components/agents/agent-chat.tsx`  
**Payload:** `{ message, agentType, skillName, chatHistory[] }`

---

#### Observations — `/api/observations/*`

| Route | Method | Tables Written | Data Written |
|---|---|---|---|
| `/api/observations/log` | POST | `interaction_logs` | Any observation event (page, learning, mood, etc.) |
| | | `student_interactions` | Mirrored row + optional `hint_requested` duplicate |
| | | `student_profile_state` | Recomputed |
| | | `bkt_skill_mastery` | If `correct` provided |
| `/api/observations/batch` | POST | Same as above (up to 200 events) |
| `/api/observations/hint` | POST | `interaction_logs` + `student_interactions` | `event_type=hint_requested` |
| `/api/observations/summary` | GET | — (read `interaction_logs`) | Aggregates only |

**Frontend caller:** `FYP_Project/lib/observations.ts` (used by `ContinuousObserver`, onboarding steps, etc.)

---

#### BKT — `/api/bkt/*`

| Route | Method | Tables Written | Data Written |
|---|---|---|---|
| `/api/bkt/skills` | GET | — (read `bkt_skill_mastery`) | |
| `/api/bkt/skills/:skillName/update` | POST | `bkt_skill_mastery` | `p_mastery`, `practice_count`, `last_practiced_at` |
| | | `student_profile_state` | Recomputed |
| `/api/bkt/state` | GET | — (read `interaction_logs`, `student_profile_state`) | May trigger recompute if missing |

**FastAPI call:** `POST /api/analyze-state` — no DB write

**Frontend caller:** `FYP_Project/app/dashboard/skills/page.tsx`

---

#### Dashboard — `/api/dashboard/*`

| Route | Method | Tables Written | Data Written |
|---|---|---|---|
| `/api/dashboard/me` | GET | — | Reads: `users`, `initial_profiles`, `interaction_logs`, `bkt_skill_mastery`, `student_profile_state` |

**Frontend caller:** `FYP_Project/app/dashboard/page.tsx`

---

### FastAPI (`backend`) — Port 8080

Express is the only caller from frontend. FastAPI endpoints below are invoked by Express or for debugging.

| Route | Method | Tables Written | Tables Read |
|---|---|---|---|
| `/api/predict/initial-profile` | POST | — | — |
| `/api/analyze-state` | POST | — | — |
| `/api/bkt/skills` | GET | — | — (CSV in memory) |
| `/api/bkt/params/{skill}` | GET | — | — |
| `/api/chat` | POST | — | — (legacy OpenAI path) |
| `/api/agent/chat` | POST | `initial_profiles` (background) | `bkt_skill_mastery`, `initial_profiles`, `interaction_logs`, `agent_memory`, `knowledge_chunks` |
| `/api/agent/router` | POST | — | — |
| `/api/agent/wellness/sync` | POST | `agent_memory` | — |
| `/api/agent/context/{user}/{skill}` | GET | — | Same 4 context tables |
| `/api/agent/memory/{user}` | GET | — | `agent_memory` |
| `/api/agent/memory/summary` | POST | — | — |
| `/api/agent/prompt-templates` | GET | — | — |

---

## Read Path Summary (Who Reads What)

```mermaid
flowchart LR
  subgraph Frontend
    FE[Next.js FYP_Project]
  end

  subgraph Express
    AUTH[/api/auth]
    ONB[/api/initial-profiling]
    CHAT[/api/chat]
    OBS[/api/observations]
    BKT[/api/bkt]
    DASH[/api/dashboard]
  end

  subgraph FastAPI
    AGENT[/api/agent/chat]
    PRED[/api/predict]
  end

  subgraph PostgreSQL
    U[(users)]
    IP[(initial_profiles)]
    IL[(interaction_logs)]
    SI[(student_interactions)]
    SPS[(student_profile_state)]
    BKT_T[(bkt_skill_mastery)]
    AM[(agent_memory)]
  end

  FE --> AUTH & ONB & CHAT & OBS & BKT & DASH
  ONB --> PRED
  CHAT --> AGENT
  AGENT --> IP & IL & BKT_T & AM

  AUTH --> U
  ONB --> U & IP & BKT_T
  CHAT --> IL & SI & SPS & BKT_T
  OBS --> IL & SI & SPS & BKT_T
  BKT --> BKT_T & SPS & IL
  DASH --> U & IP & IL & BKT_T & SPS
```

---

## Gap Analysis: Your Target vs Current

### `users`

| Target | Current | Migration note |
|---|---|---|
| `id` UUID PK | `id` INTEGER + `userId` UUID | Pick one UUID strategy; add `clerk_id` if moving to Clerk |
| `clerk_id` | Missing | Add column; stop storing `password` if Clerk-only |
| `full_name` | `name` | Rename or alias |
| `created_at` | `createdAt` | OK |

### `diagnostic_profiles`

| Target | Current | Migration note |
|---|---|---|
| Flat string columns | 4 JSONB blobs + 10+ ML columns | Either flatten JSON into columns **or** keep JSONB and add a view |
| `prior_education` | Nested in `educational_background` | Extract on write |
| `primary_language` | `cultural_context.primaryLanguage` | Extract on write |
| `commute_type`, `tech_access` | Not in form | Add to onboarding UI + column |

### `academic_progress`

| Target | Current | Migration note |
|---|---|---|
| One row per subject | 190 rows per skill in `bkt_skill_mastery` | Decide: replace BKT table vs add subject-level rollup table |
| `bloom_level` per subject | Global `initial_profiles.bloom_level` only | Academic agent would need per-subject updates |
| `last_assessed` | `last_practiced_at` per skill | Map or aggregate |

### `chat_threads`

| Target | Current | Migration note |
|---|---|---|
| `thread_id` UUID PK | No table | Create table; link LangGraph checkpointer |
| `active_agent` | Stored in `interaction_logs.metadata.agent` per message | Move to thread row |
| `status` | No concept | Add enum: active, archived, closed |
| LangGraph checkpointer | Not implemented | New Python integration point |

### `chat_messages`

| Target | Current | Migration note |
|---|---|---|
| `thread_id` FK | `session_id` string on `interaction_logs` (loose) | Normalize FK |
| `sender` User/AI | `event_type` chat_user/chat_assistant | Direct mapping |
| `content` | `chat_text` | Direct mapping |
| `message_id` UUID | `event_id` on `interaction_logs` | Rename/table split |
| pgvector `embedding` | Only on unused FastAPI `chat_messages` | Optional add to new table |

---

## Tables to Decide: Keep, Merge, or Drop

| Table | Recommendation when migrating to your 5-table model |
|---|---|
| `users` | **Keep** — extend with `clerk_id`, simplify PK strategy |
| `initial_profiles` | **Replace/rename** → `diagnostic_profiles` (+ optional `learner_predictions` if you want ML columns separate) |
| `interaction_logs` | **Split** — chat → `chat_messages`; telemetry → new `learning_events` or keep as observations table |
| `student_interactions` | **Merge or drop** — duplicate of interaction_logs for cognitive pipeline; logic must move |
| `student_profile_state` | **Keep or materialized view** — not in your 5 tables but heavily used by routing/dashboard |
| `bkt_skill_mastery` | **Keep or map** → if you still want BKT; otherwise replace with `academic_progress` |
| `agent_memory` | **Keep** — small, useful for cross-agent sync |
| `sessions`, `notifications`, FastAPI `chat_messages` | **Drop or ignore** — legacy, unused by active routes |
| `knowledge_chunks` | **Keep** if pgvector RAG stays |

---

## Suggested Target Migration Mapping

If you adopt your 5-table schema literally, code touch points:

| Area | Files to change |
|---|---|
| User auth | `Users.js`, `authControllers.js`, `FYP_Project/app/auth/*`, `auth-session.ts` |
| Onboarding | `InitialProfile.js` → `DiagnosticProfile.js`, `onboardingControllers.js`, `profile.types.ts`, onboarding steps |
| Academic progress | `bktController.js`, `cognitiveStateService.js`, `dashboardController.js`, `context_retriever.py`, skills page |
| Chat threads | New Sequelize model, `chatController.js`, FastAPI LangGraph checkpointer, remove in-memory-only reliance |
| Chat messages | `chatController.js` (`getChatHistory`, `chatWithAgent`), `agent_router.py` context reads, chat UI components |
| FastAPI mirrors | `db.py` ORM mirrors, `context_retriever.py` |
| DB boot | `server.js` sync, `db.py` `init_db()` |

---

## Quick Reference: Event Types in `interaction_logs`

| `event_type` | Source route | `chat_text` used? |
|---|---|---|
| `chat_user` | POST `/api/chat` | Yes — user message |
| `chat_assistant` | POST `/api/chat` | Yes — AI response |
| `learning_attempt` | POST `/api/observations/log` | Optional |
| `self_report` | POST `/api/observations/log` | Optional |
| `hint_requested` | POST `/api/observations/hint` or batch | No |
| `onboarding_step_next` | Frontend observations | No |
| `onboarding_step_back` | Frontend observations | No |
| `onboarding_submit` | Frontend observations | No |
| `coordinator_routing_decision` | `student_interactions` only | JSON in `message_text` |

---

## Next Step

When you are ready to change the database, share:

1. **Final table DDL** (or confirm the 5 tables above as-is)
2. **Whether to keep BKT** (`bkt_skill_mastery`) and **hidden state** (`student_profile_state`)
3. **Auth choice:** Clerk migration or keep JWT email/password
4. **Chat model:** Replace `interaction_logs` chat rows entirely vs dual-write during transition

This file will be the baseline for the migration PR.

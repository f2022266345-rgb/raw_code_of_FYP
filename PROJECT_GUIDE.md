# LUMINA – Complete Project Guide

> A comprehensive reference for anyone approaching LUMINA for the first time. Covers what the system is, how every part works, what each file does, and how all the pieces connect.

---

## 1. What Is LUMINA?

LUMINA is an AI-powered student support system built as a Final Year Project (FYP) for Pakistani university students. It acts as a personalised tutor that tracks each student's cognitive state, learning progress, emotional wellbeing, and social needs — then responds with targeted help through four specialised AI agents.

The name "LUMINA" reflects its mission: to illuminate the path through university for students who may face language barriers, socioeconomic pressures, or lack of academic guidance.

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│              Browser  (port 3000)                           │
│         Next.js 15 · TypeScript · Tailwind CSS             │
│         Clerk Auth (JWT)  ·  Zustand State Store           │
└──────────────────────┬──────────────────────────────────────┘
                       │  REST / JSON
┌──────────────────────▼──────────────────────────────────────┐
│           Express.js  (port 4000)                           │
│       Node 22 · ESM modules · Sequelize ORM                 │
│   Validates Clerk tokens → proxies to FastAPI               │
└──────────────────────┬──────────────────────────────────────┘
                       │  Internal HTTP
┌──────────────────────▼──────────────────────────────────────┐
│            FastAPI  (port 8080)                             │
│        Python 3.12 · SQLAlchemy · LangGraph                 │
│  Gemini LLM · BKT · LSTM · pgvector episodic memory        │
└──────────────────────┬──────────────────────────────────────┘
                       │  SQL (psycopg3)
┌──────────────────────▼──────────────────────────────────────┐
│           PostgreSQL  (port 5432)                           │
│        Database: FYP_backup                                 │
│        Extensions: pgvector, uuid-ossp                      │
└─────────────────────────────────────────────────────────────┘
```

**Rule of thumb:** The browser never talks directly to FastAPI. All AI/ML requests go through Express first.

---

## 3. Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Next.js 15 (App Router) | Server + client components, layouts |
| Auth | Clerk | Handles signup/login/JWT without custom code |
| State | Zustand | Lightweight global store shared across components |
| Styling | Tailwind CSS + shadcn/ui | Utility-first, accessible components |
| Animations | Framer Motion | Smooth page and component transitions |
| API Gateway | Express.js (ESM) | Token validation, rate limiting, DB writes |
| ORM (Express) | Sequelize | Model-based DB access from JavaScript |
| AI/ML Server | FastAPI | Python ecosystem: PyTorch, scikit-learn, LangGraph |
| ORM (FastAPI) | SQLAlchemy | Raw SQL + ORM hybrid |
| LLM | Google Gemini 2.5 Flash | Conversational AI, embeddings |
| Agent Framework | LangGraph | Multi-agent orchestration with state graphs |
| Knowledge Tracing | Bayesian Knowledge Tracing (BKT) | Skill mastery estimation |
| Deep Learning | PyTorch LSTM | Predicts next-problem correctness |
| Vector Search | pgvector | Semantic episodic memory retrieval |
| Database | PostgreSQL 17 | Primary persistent store |

---

## 4. Repository Structure

```
Project Code/
├── FYP_Project/               ← Next.js frontend
│   ├── app/                   ← App Router pages
│   ├── components/            ← Reusable UI components
│   ├── lib/                   ← API helpers, store, utilities
│   └── public/                ← Static assets
│
├── backend-express/           ← Express.js API gateway
│   ├── controllers/           ← Business logic per domain
│   ├── routes/                ← Route definitions
│   ├── model/                 ← Sequelize ORM models
│   ├── middlewares/           ← Clerk auth middleware
│   ├── services/              ← Background jobs, helpers
│   └── server.js              ← Entry point
│
├── backend/                   ← FastAPI ML/AI server
│   ├── routers/               ← FastAPI route files
│   ├── services/              ← Core AI/ML services
│   ├── models/                ← PyTorch model definitions
│   ├── migrations/            ← SQL schema files
│   ├── main.py                ← FastAPI app entry point
│   ├── db.py                  ← SQLAlchemy engine + ORM base
│   └── ai_service.py          ← ML inference (initial profiling)
│
└── scripts/                   ← Migration and seeding scripts
```

---

## 5. Database Schema

All tables live in PostgreSQL database `FYP_backup`.

### 5.1 Authentication & Users

**`users`** — Created by the Clerk webhook when a student signs up.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key (Clerk user ID converted to UUID) |
| email | VARCHAR | Student email |
| name | VARCHAR | Display name |
| created_at | TIMESTAMPTZ | Sign-up time |

### 5.2 Onboarding & Profile

**`initial_profiles`** — Raw JSONB dump of the onboarding form + ML predictions.

| Column | Type | Description |
|--------|------|-------------|
| userId | UUID FK | Links to users |
| educationalBackground | JSONB | University, program, English level |
| learningPreferences | JSONB | Study pace, language preference |
| culturalContext | JSONB | City, family pressure, first-gen status |
| aiPrediction | JSONB | ML output (bloom level, language risk, agents) |
| bloomLevel | INT | Bloom's Taxonomy level (1-6) |
| activeAgents | TEXT[] | Which agents are enabled for this student |

**`diagnostic_profiles`** — Flat structured version of the same data for SQL queries.

**`academic_progress`** — One row per course the student is enrolled in.

**`social_metrics`** — Cultural and social context (first-gen, family support).

**`wellness_logs`** — Time-series wellbeing entries (stress, mood, source).

### 5.3 Digital Twin Tables (added in migration 002)

**`student_profiles`** — Extended student profile for the Digital Twin.

| Column | Type | Description |
|--------|------|-------------|
| user_id | UUID FK | Links to users |
| language_barrier_risk | FLOAT | 0.0–1.0 (higher = more at-risk) |
| english_proficiency | VARCHAR | beginner/intermediate/advanced |
| wellness_support_needed | BOOL | Flagged during onboarding |
| social_support_needed | BOOL | Flagged during onboarding |

**`cognitive_state`** — Real-time snapshot of the student's mental state.

| Column | Type | Description |
|--------|------|-------------|
| current_bloom_level | INT | 1–6 (Remember → Create) |
| cognitive_state | VARCHAR | developing/flow_state/critical_struggle/etc. |
| engagement_level | VARCHAR | engaged/disengaged |
| frustration_estimate | FLOAT | 0.0–1.0 |
| motivation_index | FLOAT | 0.0–1.0 |
| learning_velocity | FLOAT | Recent correct-answer rate (rolling avg) |

**`learning_interactions`** — Append-only log of every problem attempt.

| Column | Type | Description |
|--------|------|-------------|
| user_id | UUID FK | Student |
| skill_id | INT | Which skill was practiced |
| correct | BOOL | Did they get it right? |
| time_on_task_ms | INT | Milliseconds spent on the problem |
| hints_used | INT | How many hints requested |
| mood | VARCHAR | Self-reported mood (optional) |

**`skill_mastery`** — BKT mastery state per (student, skill) pair.

| Column | Type | Description |
|--------|------|-------------|
| p_mastery | FLOAT | P(knows skill) — updated after every attempt |
| p_init | FLOAT | Prior probability of knowing the skill |
| p_transit | FLOAT | P(learns from one attempt) |
| p_guess | FLOAT | P(correct given not mastered) |
| p_slip | FLOAT | P(wrong given mastered) |

**`wellness_state`** — Aggregated wellness for the Digital Twin.

**`digital_twin_predictions`** — LSTM/model outputs per student.

| Column | Type | Description |
|--------|------|-------------|
| predicted_next_problem_correctness | FLOAT | 0.0–1.0 (LSTM output) |
| at_risk_probability | FLOAT | Risk of academic failure |
| recommended_agent_type | VARCHAR | Which agent to route to next |
| intervention_urgency | VARCHAR | normal/high |

**`learning_progress`** — Topic-level progress tracking.

**`student_digital_twin`** — A VIEW joining all the above for easy reads.

### 5.4 AI Memory

**`agent_memory`** — pgvector table. Stores embeddings of past conversations so agents can retrieve relevant context via similarity search.

| Column | Type | Description |
|--------|------|-------------|
| user_id | UUID FK | Student |
| summary_text | TEXT | Text summary of an interaction |
| embedding | VECTOR(768) | Gemini text-embedding-004 embedding |

**`bkt_skill_mastery`** — Express-managed copy of skill mastery (synced from FastAPI BKT).

---

## 6. How Authentication Works

1. Student signs up/logs in via **Clerk** on the frontend.
2. Clerk issues a **JWT token**.
3. Every frontend API call includes this token in the `Authorization: Bearer <token>` header via the `fetchWithClerkAuth` helper (`FYP_Project/lib/api.ts`).
4. Express middleware (`backend-express/middlewares/clerkMiddleware.js`) verifies the JWT with Clerk's public keys.
5. If valid, Express attaches `req.user.userId` (the PostgreSQL UUID) to the request object.
6. Express controllers use `req.user.userId` — **never** `req.user.id`.
7. FastAPI endpoints do not do their own auth — they trust Express to validate tokens first.

When a new user signs up, a **Clerk webhook** fires to `POST /api/webhooks/clerk`. The webhook handler creates a row in the `users` table, converting the Clerk user ID to a UUID stored in the database.

---

## 7. Onboarding Pipeline

When a student completes the onboarding form, Express processes it in 9 steps:

```
Step 1  → Map form data to structured fields (profileMapper.js)
Step 2  → Upsert InitialProfile (raw JSONB to initial_profiles)
Step 3  → Upsert DiagnosticProfile (structured flat columns)
Step 4  → Seed AcademicProgress rows (one per course)
Step 5  → Upsert SocialMetrics (cultural context)
Step 6  → Create initial WellnessLog entry
Step 7  → Call FastAPI /api/predict/initial-profile (ML predictions)
Step 8  → Update InitialProfile with ML outputs + active agents
Step 9  → Initialize Digital Twin (POST /api/digital-twin/initialize)
```

**Key file:** `backend-express/controllers/onboardingControllers.js`

Step 7 calls FastAPI, which runs `ai_service.py`:
- Uses a trained random forest / rule-based model to predict Bloom level (1–6)
- Estimates language barrier risk (0.0–1.0)
- Flags whether wellness/social/academic support is needed
- Saves a pgvector embedding of the prediction for future similarity searches

Step 9 is non-fatal — if it fails, onboarding still completes.

---

## 8. How the AI Agents Work

### 8.1 Overview

LUMINA has four AI agents. Each is a specialised personality built on top of Gemini 2.5 Flash.

| Agent | Colour | Responsibility |
|-------|--------|---------------|
| Academic | Blue | Study plans, skill gaps, Bloom-level content |
| Social | Emerald | Study groups, networking, Pakistani university culture |
| Wellness | Pink | Stress, burnout, mental health check-ins |
| Coordinator | Violet | Routing, holistic summaries, cross-agent advice |

### 8.2 Chat Flow

```
User types message
        ↓
POST /api/chat/agent (Express)
        ↓
Express verifies Clerk token → gets userId
        ↓
Express POST /api/agent/chat (FastAPI)
        ↓
FastAPI agent_router.py
  1. Loads student context from DB
  2. Retrieves episodic memories (pgvector similarity search)
  3. Builds system prompt (student profile + memories + BKT summary)
  4. Routes to the right agent via LangGraph
  5. Streams Gemini response back
        ↓
Response streams to browser
```

**Key file:** `backend/routers/agent_router.py`

### 8.3 LangGraph in LUMINA

LangGraph is a framework for building stateful multi-agent systems. In LUMINA it works as follows:

1. A **StateGraph** is defined with a shared `AgentState` (contains: messages, current agent, student context, routing decision).
2. The **Coordinator node** reads the student's question and current cognitive state, then decides which specialist agent should respond.
3. The **selected agent node** (Academic/Social/Wellness) receives the state with the routing decision and generates the response using its own system prompt.
4. All nodes share read access to the student context, but each has its own personality instructions and knowledge focus.
5. Edges in the graph are conditional: if the coordinator routes to "academic", the graph traverses the Academic edge.

**Key file:** `backend/services/gemini_agent.py` — contains the LangGraph graph definition, all node functions, and the Gemini API calls.

### 8.4 System Prompt Construction

Every chat request builds a rich system prompt that includes:
- Student's name, university, major
- Current Bloom level and cognitive state
- Top 3 weak skills from BKT
- Language barrier risk (determines whether to simplify English)
- Relevant episodic memories retrieved by pgvector similarity
- Agent-specific personality instructions

This means the agents "know" the student before the first message — they are not starting from scratch.

---

## 9. Bayesian Knowledge Tracing (BKT)

BKT is the algorithm that tracks how well a student knows each skill.

### 9.1 How It Works

BKT models each skill as a hidden binary variable: the student either "knows" it or they don't. Four parameters control the model:

| Parameter | Symbol | Meaning |
|-----------|--------|---------|
| Prior | P(L₀) | Probability the student already knows the skill |
| Transit | P(T) | Probability of learning from one attempt |
| Guess | P(G) | Probability of correct answer without knowing |
| Slip | P(S) | Probability of wrong answer despite knowing |

After each problem attempt, the posterior probability is updated:

```
If correct:  P(L|correct)  = P(L) × (1 - P(S)) / [P(L)(1-P(S)) + (1-P(L))×P(G)]
If incorrect: P(L|wrong)   = P(L) × P(S)        / [P(L)×P(S)    + (1-P(L))×(1-P(G))]

Then apply transit: P(L_new) = P(L|obs) + (1 - P(L|obs)) × P(T)
```

### 9.2 Where Parameters Come From

The BKT parameters were trained on the **ASSISTments** dataset (a public educational dataset of ~300,000 student interactions). The trained parameters are stored in `backend/bkt_parameters_trained.csv` and loaded into memory at startup (`main.py` lifespan).

### 9.3 Code Location

- **Parameter loading:** `backend/main.py` → `_load_bkt_csv()`
- **Single-step update:** `backend/services/digital_twin_updater.py` → `_bkt_update()`
- **Database storage:** `skill_mastery` table, one row per (student, skill)
- **Express sync:** `backend-express/controllers/bktController.js`

---

## 10. The Digital Twin

The Digital Twin is a persistent, evolving model of each student that lives in the database and is updated after every learning interaction.

### 10.1 What It Models

```
Digital Twin
├── Cognitive State     (bloom_level, frustration, motivation, velocity)
├── Skill Mastery       (BKT p_mastery per skill)
├── Wellness State      (stress_level_30d, burnout_risk)
├── Predictions         (next_problem_correctness, at_risk_probability)
└── Learning Progress   (topic, problems_completed, milestones)
```

### 10.2 Lifecycle

1. **Created** during onboarding (Step 9) — seeded with baseline values from ML predictions.
2. **Updated** after every interaction via `DigitalTwinUpdater` (`backend/services/digital_twin_updater.py`).
3. **Read** by the frontend `DigitalTwinDashboard` component and by agents when building system prompts.

### 10.3 The LSTM Model

`backend/models/cognitive_twin_lstm.py` defines `CognitiveTwinLSTM`:
- **Architecture:** 2-layer LSTM with skill embeddings
- **Input:** Sequences of `(correct, time_on_task, hints_used, attempt_count)` + skill IDs
- **Output:** Single float — predicted probability that the next answer will be correct
- **Trained on:** ASSISTments educational dataset
- **Model file:** `backend/safe_cognitive_twin.pth`

The LSTM captures temporal patterns — for example, a student who answers correctly but takes longer and longer may be approaching their cognitive limit, even if they're still getting answers right.

### 10.4 Update Pipeline (DigitalTwinUpdater)

Every interaction triggers:

```
1. Log to learning_interactions
2. BKT update → new p_mastery for the skill
3. Compute cognitive state (frustration, motivation, Bloom)
4. Assess affective state (stress delta from mood + confidence)
5. LSTM inference → predicted next-problem correctness
6. Determine intervention (immediate_support / scaffold / advance / etc.)
7. Persist to cognitive_state, wellness_state, digital_twin_predictions
```

### 10.5 Intervention Logic

| Condition | Intervention | Recommended Agent |
|-----------|-------------|-------------------|
| frustration > 0.75 or critical_struggle | immediate_support | Wellness |
| predicted_correctness < 0.35 or disengaged | re_engage | Coordinator |
| productive_struggle | scaffold | Academic |
| flow_state + high prediction | advance_difficulty | Academic |
| Default | continue | Coordinator |

---

## 11. pgvector Episodic Memory

pgvector is a PostgreSQL extension that allows storing and searching high-dimensional vectors.

### 11.1 How It's Used

Every significant interaction (e.g., a full conversation turn) is:
1. Summarised into a text string
2. Embedded using Gemini's `text-embedding-004` model (768 dimensions)
3. Stored in the `agent_memory` table alongside the original text

When building a system prompt for a new chat request:
1. The current message is embedded
2. A cosine similarity search retrieves the top 3 most relevant past memories
3. These memories are injected into the system prompt

This gives agents "long-term memory" — they can reference what was discussed weeks ago.

**Key function:** `backend/services/gemini_agent.py` → `generate_embedding()`, `retrieve_memories()`

---

## 12. Frontend Structure

### 12.1 Pages (`FYP_Project/app/`)

| Route | File | Description |
|-------|------|-------------|
| `/` | `page.tsx` | Public landing page |
| `/onboarding` | `onboarding/page.tsx` | Multi-step onboarding form |
| `/dashboard` | `dashboard/page.tsx` | Main dashboard (Overview + Chat views) |
| `/dashboard/chat` | `dashboard/chat/page.tsx` | Full-screen chat hub |
| `/dashboard/skills` | `dashboard/skills/page.tsx` | BKT skill mastery visualisation |
| `/dashboard/analytics` | `dashboard/analytics/page.tsx` | Progress analytics |
| `/dashboard/agent/[type]` | `dashboard/agent/[type]/page.tsx` | Individual agent detail page |

### 12.2 Key Components (`FYP_Project/components/`)

**Dashboard:**
- `dashboard/agent-chat.tsx` — The core chat component. Takes `agentType`, `agentColor`, etc. as props. Manages message history, sends requests to Express, renders streamed responses.
- `dashboard/DigitalTwinCard.tsx` — Shows Bloom level, engagement, stress, at-risk score, and top skills as progress bars.
- `dashboard/DigitalTwinDashboard.tsx` — Wraps `DigitalTwinCard` with a 7-day accuracy bar chart and a Refresh button.

**Layout:**
- `layout/header.tsx` — Fixed navigation header with glassmorphism scroll effect.
- `layout/footer.tsx` — Footer with newsletter form.

### 12.3 State Management (`FYP_Project/lib/`)

**`store.ts`** — Zustand store. Hydrated once on dashboard load from `GET /api/dashboard/me`.

Key slices:
- `user` — name, email, bloomLevel, languageBarrierRisk, activeAgents
- `bktSummary` — avgMastery, masteredCount, totalSkills
- `hiddenState` — engagementEstimate, readinessEstimate, masterySummary
- `chatHistorySummary` — totalMessages, lastAgent

**`api.ts`** — `fetchWithClerkAuth(url, options)`: wraps `fetch()` with the Clerk JWT token. Always returns a `Response` object — call `.json()` on it.

**`digital-twin-api.ts`** — Functions: `getDigitalTwin()`, `reportInteraction()`, `getAnalytics()`, `initializeDigitalTwin()`.

---

## 13. Express API Endpoints

Base URL: `http://localhost:4000`

All routes except webhooks require `Authorization: Bearer <clerk_token>`.

| Method | Path | Controller | Description |
|--------|------|-----------|-------------|
| POST | `/api/initial-profiling` | onboardingControllers | Submit onboarding form |
| GET | `/api/dashboard/me` | dashboardController | Get full dashboard data |
| GET | `/api/bkt/skills` | bktController | Get all BKT skill mastery |
| POST | `/api/bkt/update` | bktController | Log a skill attempt |
| POST | `/api/chat/agent` | chatController | Send chat message to AI agent |
| GET | `/api/observations` | observationsController | Get student observations |
| GET | `/api/digital-twin/student` | digitalTwinController | Get this student's Digital Twin |
| POST | `/api/digital-twin/update` | digitalTwinController | Log interaction + update twin |
| GET | `/api/digital-twin/analytics` | digitalTwinController | Get analytics trend |
| POST | `/api/digital-twin/initialize` | digitalTwinController | Init twin (onboarding) |
| POST | `/api/webhooks/clerk` | webhookRoutes | Clerk user sync webhook |

---

## 14. FastAPI Endpoints

Base URL: `http://localhost:8080`

Called internally by Express — not directly from the browser.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/predict/initial-profile` | ML inference for onboarding |
| POST | `/api/agent/chat` | LangGraph multi-agent chat |
| POST | `/api/analyze-state` | Trend engine cognitive state analysis |
| GET | `/api/bkt/skills` | All BKT skill parameters |
| GET | `/api/bkt/params/{skill}` | Single skill BKT parameters |
| GET | `/api/digital-twin/health` | Digital Twin service health |
| POST | `/api/digital-twin/initialize` | Seed Digital Twin for new student |
| GET | `/api/digital-twin/student/{user_id}` | Full Digital Twin data |
| POST | `/api/digital-twin/update` | Update twin from interaction |
| GET | `/api/digital-twin/analytics/{user_id}` | Analytics trend |

---

## 15. Key File Reference

### Backend (FastAPI)

| File | Role |
|------|------|
| `main.py` | App entry, BKT CSV loader, CORS, router mounts |
| `db.py` | SQLAlchemy engine, `get_db()` dependency, `init_db()` |
| `ai_service.py` | Initial profiling ML model (random forest + rules) |
| `routers/agent_router.py` | `/api/agent/chat` — LangGraph orchestration endpoint |
| `routers/digital_twin_router.py` | `/api/digital-twin/*` endpoints |
| `services/gemini_agent.py` | Gemini client, embeddings, prompt building, LangGraph graph |
| `services/digital_twin_factory.py` | Bulk Digital Twin creation (ASSISTments seeding) |
| `services/digital_twin_updater.py` | Real-time twin update pipeline |
| `services/trend_engine.py` | Cognitive state trend analysis (frustration/accuracy/boredom) |
| `services/scheduler.py` | APScheduler background jobs |
| `models/cognitive_twin_lstm.py` | PyTorch 2-layer LSTM definition |
| `bkt_parameters_trained.csv` | Trained BKT params for ~400 skills (from ASSISTments) |
| `safe_cognitive_twin.pth` | Trained LSTM weights |
| `migrations/002_digital_twin_tables.sql` | Digital Twin DB schema |

### Backend Express

| File | Role |
|------|------|
| `server.js` | Express app, middleware setup, route mounting |
| `controllers/onboardingControllers.js` | 9-step onboarding pipeline |
| `controllers/chatController.js` | Proxies chat messages to FastAPI |
| `controllers/bktController.js` | BKT skill mastery CRUD |
| `controllers/digitalTwinController.js` | Proxies Digital Twin API calls to FastAPI |
| `controllers/dashboardController.js` | Aggregates data for dashboard |
| `middlewares/clerkMiddleware.js` | Verifies Clerk JWT, sets `req.user.userId` |
| `services/profileMapper.js` | Maps onboarding form to structured DB fields |
| `services/cronJobs.js` | Scheduled background tasks |
| `model/index.js` | Sequelize model loader |
| `config/database.js` | Sequelize connection config |

### Frontend (Next.js)

| File | Role |
|------|------|
| `app/dashboard/page.tsx` | Main dashboard — Overview + Chat Agents views |
| `components/dashboard/agent-chat.tsx` | Core chat UI component |
| `components/dashboard/DigitalTwinDashboard.tsx` | Twin stats + chart widget |
| `components/dashboard/DigitalTwinCard.tsx` | Bloom/engagement/stress display card |
| `lib/api.ts` | `fetchWithClerkAuth` — authenticated fetch wrapper |
| `lib/store.ts` | Zustand global state store |
| `lib/digital-twin-api.ts` | Digital Twin API client functions |

---

## 16. Environment Variables

### `backend/.env`
```
DATABASE_URL=postgresql+psycopg://postgres:admin@localhost:5432/FYP_backup
GEMINI_API_KEY=<your_key>
GEMINI_MODEL=gemini-2.5-flash
OPENAI_API_KEY=   # Not used — Gemini is primary
```

### `backend-express/.env`
```
DATABASE_URL=postgresql://postgres:admin@localhost:5432/FYP_backup
FASTAPI_BASE_URL=http://localhost:8080
CLERK_SECRET_KEY=<your_key>
CLERK_WEBHOOK_SECRET=<your_key>
PORT=4000
```

### `FYP_Project/.env.local`
```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<your_key>
CLERK_SECRET_KEY=<your_key>
NEXT_PUBLIC_API_URL=http://localhost:4000
```

---

## 17. How to Run the Project

### Prerequisites
- PostgreSQL 17 running locally
- Node.js 22+
- Python 3.12+
- A Clerk application (for auth keys)
- A Google AI Studio API key (for Gemini)

### Start the Databases
```bash
# Ensure PostgreSQL is running
# Apply migrations if needed:
psql "postgresql://postgres:admin@localhost:5432/FYP_backup" -f backend/migrations/002_digital_twin_tables.sql
```

### Start FastAPI
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### Start Express
```bash
cd backend-express
npm install
npm run dev       # or: node server.js
```

### Start Next.js
```bash
cd FYP_Project
npm install
npm run dev
```

Open http://localhost:3000.

---

## 18. Data Flow: A Student's Journey

```
1. Student signs up
   → Clerk webhook → users table row created

2. Student completes onboarding
   → 9-step pipeline → initial_profiles, diagnostic_profiles, skill_mastery seeded
   → FastAPI ML → bloom_level predicted, language_barrier_risk calculated
   → Digital Twin initialized with baseline values

3. Student opens dashboard
   → GET /api/dashboard/me → aggregates all profile data
   → DigitalTwinDashboard shows cognitive state, skills, predictions

4. Student chats with Academic agent
   → POST /api/chat/agent (Express) → POST /api/agent/chat (FastAPI)
   → pgvector retrieves 3 relevant memories
   → System prompt built with student's bloom level, weak skills, language risk
   → LangGraph routes to Academic agent
   → Gemini generates personalised response
   → Response streamed back

5. After chat interaction
   → DigitalTwinUpdater updates: skill_mastery, cognitive_state, wellness_state
   → digital_twin_predictions updated with new LSTM inference
   → If frustration > 0.75: recommended_agent = wellness (intervention triggered)

6. Next session
   → Agents have memory of past conversations via pgvector
   → Digital Twin reflects accumulated learning history
   → Bloom level may have advanced if mastery thresholds were met
```

---

## 19. Design Decisions & Tradeoffs

**Why three servers?** The three-tier architecture separates concerns: Express handles auth and rate limiting without Python overhead; FastAPI gives access to PyTorch and the scientific Python ecosystem; Next.js handles SSR and client routing. The tradeoff is operational complexity.

**Why Gemini instead of OpenAI?** Cost and Pakistani market access. Gemini 2.5 Flash provides strong multilingual capability at lower cost, and handles Urdu-influenced English well.

**Why BKT instead of IRT or deep knowledge tracing?** BKT is interpretable (you can show students their mastery probability) and has well-understood parameters trainable from the ASSISTments dataset. IRT requires item difficulty data we don't have. Deep knowledge tracing (DKT) is the LSTM component — both are used in tandem.

**Why pgvector for memory?** Relational databases for structured data + vector search in the same engine avoids a separate vector database. This keeps the deployment simple for an FYP context.

**Why Clerk?** Building auth from scratch for a university project is risky (security holes). Clerk handles OAuth, magic links, JWT issuance, and webhooks out of the box.

---

*This guide was generated on 2026-06-20 and reflects the state of LUMINA at that date.*

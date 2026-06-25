# Lumina Multi-Agent AI Tutoring System
**Detailed Implementation & Architecture Guide (v2)**

This document provides a highly detailed overview of the Lumina backend ecosystem, which operates as a dual-backend microservice architecture bridging standard RESTful business logic with heavy asynchronous AI orchestration and state tracking.

---

## 1. System Architecture Overview

The system consists of two distinct backend applications communicating over HTTP, sharing a single **PostgreSQL** database:

### 1.1 Express API Gateway (`backend-express`)
- **Environment**: Node.js, Express, Sequelize, Clerk Auth. Runs on `PORT 4000`.
- **Purpose**: Acts as the gatekeeper. Handles user authentication via Clerk, manages relational structured data, and acts as a proxy for the AI engine to prevent long-running LLM inferences from blocking standard web requests.
- **Key Flow**: Receives standard JSON from the Next.js frontend, validates session tokens, performs CRUD operations, and forwards AI-intensive tasks to FastAPI.

### 1.2 FastAPI AI Engine (`backend`)
- **Environment**: Python 3, FastAPI, SQLAlchemy, `pgvector`, Google GenAI (`google-genai` SDK), LangGraph. Runs on `PORT 8080`.
- **Purpose**: Handles Machine Learning inferences (Initial Profiling via Random Forest), calculates Bayesian Knowledge Tracing (BKT) skill updates, determines latent student states (Trend Engine), and orchestrates multi-agent LLM logic via Gemini.
- **Key Flow**: Pulls massive context from the shared DB, computes cognitive rules, triggers LangGraph workflows, and returns LLM streams or JSON decisions.

---

## 2. Deep Dive: Database Modeling

The database uses PostgreSQL with the `pgvector` extension. Express owns the schema creation (`alter: true`), while FastAPI mirrors these tables via SQLAlchemy `extend_existing=True` to read them, while also managing its own AI-specific tables.

### 2.1 Managed by Express (Sequelize)
- **`Users`**: Standard user details linked to Clerk.
- **`InitialProfile`**: A JSONB-heavy store containing raw onboarding forms (`educationalBackground`, `learningPreferences`, `culturalContext`) alongside ML predictions (`languageBarrierRisk`, `bloomLevelPredicted`) and cognitive rules.
- **`DiagnosticProfile`**: Flattened, structured version of user demographics and tech access.
- **`AcademicProgress`**: Tracks per-course `currentBloomLevel` and `completedTopics`.
- **`SocialMetrics` & `WellnessLog`**: Logs cultural challenges (e.g., first-gen student) and tracks sentiment markers (e.g., stress indicators) respectively.
- **`ChatThread` & `ChatMessage`**: Persists conversation history with `uiCardMetadata`.
- **`InteractionLog`**: Highly granular event log tracking `sentiment_score`, `mood`, `hints_used`, and `response_time_ms`.
- **`BktSkillMastery`**: Stores BKT parameters per student per skill (`p_mastery`, `p_init`, `p_transit`, `p_guess`, `p_slip`, `practice_count`).

### 2.2 Managed by FastAPI (SQLAlchemy / pgvector)
- **`agent_memory`**: Real-time cross-agent synchronization table. If the Wellness Agent detects anxiety, it writes here. The Academic Agent reads this table instantly to adjust its tone.
- **`student_model_embeddings`**: A 1536-dimensional `pgvector` table storing an AI-summarized "vibe check" of the student's profile.
- **`episodic_memory`**: A 1536-dimensional `pgvector` table storing summarized paragraphs of past tutoring sessions, allowing the agent to recall previous conversations via Cosine Similarity search.
- **`knowledge_chunks`**: Stores vector embeddings of curriculum content for RAG scaffolding.

---

## 3. Data Flow & Execution Pipelines

### 3.1 The Onboarding Pipeline (`onboardingControllers.js`)
When a student submits the onboarding form:
1. **Receive Data**: Express receives `educationalBackground`, `learningPreferences`, and `culturalContext`.
2. **Structural Mapping**: Express maps the data and creates/upserts rows into `DiagnosticProfile`, `AcademicProgress`, `SocialMetrics`, and an initial `WellnessLog`.
3. **ML Prediction Request**: Express issues a `POST` request to FastAPI's `/api/predict/initial-profile`.
4. **FastAPI Inference**: Python runs the raw JSON through a serialized scikit-learn pipeline (Random Forest) to predict the student's starting `bloom_level_predicted`, `language_barrier_risk` (0.2 or 0.7), and flags for `wellness_support_needed` and `social_support_needed`.
5. **Rules Derivation**: Express uses the prediction to generate `cognitiveRules` (e.g., chunking="medium-chunks", pacing) and derives `activeAgents` (e.g., Academic + Wellness).
6. **Persistence & Response**: The `InitialProfile` is updated with all ML outputs, and a dashboard-ready payload is returned to the frontend.

### 3.2 The Multi-Agent Streaming Chat Flow (`chatController.js` -> `agent_router.py`)
When a student types a message in the chat:
1. **Frontend Request**: Hits Express `/api/chat`.
2. **Context Assembly (Express)**: 
   - Looks up the active `ChatThread`.
   - Writes the user's message to `ChatMessage`.
   - Queries `AcademicProgress` for the average Bloom level.
   - Formats a payload containing the recent 12 messages from the DB, the frontend window, and an `orchestrationContext`.
3. **Stream Initiation**: Express forwards this to FastAPI's `/api/agent/stream`.
4. **LangGraph Invocation (FastAPI)**:
   - FastAPI spins up the LangGraph workflow (`app.graph.workflow`).
   - Edges route from `gateway` -> `coordinator`.
   - The Coordinator decides the target agent (Academic, Social, or Wellness).
5. **State Engine (`state_engine.py`)**: 
   - `context_retriever.py` queries BKT, InteractionLog, AgentMemory, and performs a semantic search on `EpisodicMemory` via `gemini-embedding-001`.
   - Evaluates the state:
     - **STRUGGLING**: Triggered if `p_mastery < 0.4` or `language_barrier_risk > 0.6`. Uses "Socratic Tutor" persona and forces pgvector scaffolding.
     - **INTELLIGENT**: Triggered if `p_mastery > 0.7` or `bloom_level >= 4`. Uses "Peer-to-Peer" persona for concise, advanced answers.
     - **DEVELOPING**: The default. Uses "Encouraging Coach".
   - Renders a strict, < 150-token system prompt containing mood, BKT stats, and cognitive state.
6. **LLM Generation**: Gemini models (configured via the official `google-genai` SDK) stream tokens back through the LangGraph async event stream (`astream_events(version="v2")`).
7. **Proxy to Frontend**: Express catches the SSE stream from FastAPI and proxies it directly to the Next.js frontend, resulting in real-time typewriter effects.
8. **Asynchronous Post-Processing**: Once complete, FastAPI triggers background tasks to extract latent profile updates (did the student mention anxiety?) and update `EpisodicMemory`. Express saves the final assistant message to `ChatMessage`.

### 3.3 Bayesian Knowledge Tracing & Trend Engine
- **BKT Engine**: Express hits `/api/bkt` endpoints to update the `bkt_skill_mastery` table. BKT uses 4 parameters (`p_init`, `p_transit`, `p_guess`, `p_slip`) to probabilistically determine `p_mastery`.
- **Trend Engine**: FastAPI's `/api/analyze-state` looks at arrays of recent accuracy, response times, and frustration scores to output a discrete cognitive label like `CRITICAL_STRUGGLE` or `FLOW_STATE`. This label is passed into the prompt engineering pipeline.

### 3.4 Cron Jobs & Automated Analysis
- **Express Cron (`services/cronJobs.js`)**: Triggers regular intervals.
- Every 2 weeks, it sends a payload to FastAPI's `/metrics/analyze`.
- FastAPI invokes `semester_graph.py` to evaluate the student's holistic performance, potentially bumping their Bloom level or flagging them for manual human intervention.

---

## 4. Key Libraries & Integrations
- **AI Models**: Google Gemini via `google-genai` (Node and Python). Text models: `gemini-flash-latest` (or GitHub open equivalents). Embeddings: `gemini-embedding-001`.
- **LangGraph**: Used extensively in Python (`app.graph.workflow.py`) to manage stateful, interruptible multi-agent flows.
- **Clerk**: Handles all user authentication seamlessly via standard JWT verification in Express.
- **pgvector**: Natively computes Cosine Distances directly in Postgres to find semantically relevant curriculum scaffolding and past memories based on the user's current chat query.

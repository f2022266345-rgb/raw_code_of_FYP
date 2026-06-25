# Lumina Multi-Agent AI Tutoring System
**Project Overview & Architecture**

This project is a culturally-aware, multi-agent AI tutoring ecosystem tailored for university students. The architecture uses a microservices approach with a two-part backend to separate business logic/gateway operations from heavy AI inferences and language model integrations. 

## System Architecture Overview

The system is composed of three primary layers:
1. **Frontend**: A Next.js application built for the user interface, dashboard, onboarding forms, and interactive chat widget.
2. **Backend Gateway (`backend-express`)**: A Node.js/Express service that acts as the primary API Gateway, handles Authentication (via Clerk), manages core Database schemas via Sequelize, and serves as the intermediary for UI requests.
3. **AI Inference & Orchestration (`backend`)**: A Python/FastAPI service responsible for complex intelligence layers including Bayesian Knowledge Tracing (BKT), latent cognitive state inference, LangGraph workflows, and invoking Google Gemini (via Google GenAI official SDK) for text and embeddings.

Both backends share a single **PostgreSQL** database. The database uses the `pgvector` extension to handle vector embeddings for semantic search and episodic memory.

---

## Data Flow & Core Systems

### 1. Onboarding Pipeline Flow
- **Frontend** posts raw onboarding form data to `Express POST /api/initial-profiling`.
- **Express** securely stores this raw data into the `InitialProfile` table (e.g. educational background, cultural context).
- **Express** calls the **FastAPI ML Endpoint** `POST /api/predict/initial-profile` to run inferences.
- **FastAPI** returns predictions such as `bloom_level_predicted`, `language_barrier_risk`, `learning_barriers_score`, and support needs flags (wellness, social). FastAPI also embeds this context to `pgvector` memory.
- **Express** computes cognitive rules (pacing, chunking, language scaffolding) based on the predictions, activates necessary agents, updates the database, and returns a dashboard-ready payload.

### 2. Multi-Agent Chat Flow
- **Frontend** sends a chat message along with current session history to `Express POST /api/chat`.
- **Express** verifies the user (Clerk), pulls recent persisted chat histories from the `InteractionLog` or `ChatMessages` table, and forwards both histories + the new message to `FastAPI POST /api/agent/chat`.
- **FastAPI**:
  1. Pulls the student context (BKT mastery, AI prediction data, cognitive states) from database mirrors.
  2. Detects the student's current state via a Trend Engine (identifying flow state, frustration, or disengagement).
  3. Uses a lightweight routing logic to determine which agent to use (Academic, Wellness, Social, or Coordinator).
  4. Generates an AI summary of previous chat context and applies strict dynamic prompt engineering templates depending on the inferred student state.
  5. Performs token-optimized LLM calls using the `google-genai` library (Gemini models).
  6. Analyzes the latest conversation loop asynchronously to dynamically update the student's profile (like wellness support flags) based on what was just discussed.
- **FastAPI** returns the formatted string, next action, and metadata back to **Express**, which forwards it to the **Frontend**.

### 3. Asynchronous Operations & Cron Jobs
- **Express** manages cron jobs (like `cronJobs.js`) to trigger periodic evaluations (e.g., executing the Semester LangGraph Workflow via FastAPI to analyze student performance every 2 weeks).
- **FastAPI** contains LangGraph nodes (`app/graph/workflow.py`) mapping out gateway -> coordinator -> academic/wellness/social routes, acting dynamically based on context checkpointers.

---

## Component Breakdown

### Express Backend (`backend-express`)
**Port**: 4000 
**Key Technologies**: Node.js, Express, Sequelize, Clerk

- **Role**: Standard API Gateway.
- **Auth Layer**: Middleware checks Clerk Auth tokens (`middlewares/clerkMiddleware.js`).
- **Database Modeler**: Sequelize `sync({ alter: true })` owns the structural deployment of standard tables.
- **Directories**:
  - `/routes` & `/controllers`: Handle business endpoints (`bktRoutes`, `chatRoutes`, `OnboardingRoutes`).
  - `/model`: Sequelize definitions for core entities.
  - `/services`: Houses logic like Cron Jobs to ping the FastAPI server.

### FastAPI AI Engine (`backend`)
**Port**: 8080
**Key Technologies**: Python, FastAPI, SQLAlchemy, pgvector, Google GenAI (Gemini), LangGraph.

- **Role**: Intelligence layer. Evaluates embeddings, builds prompts, controls the LLMs, processes logic loops.
- **Integration**: Operates `gemini-embedding-001` to generate embeddings and pad them to 1536d to match database vectors seamlessly.
- **Agent Orchestration**: `routers/agent_router.py` maps out the core AI pipeline and streaming logic, delegating instructions to `services/gemini_agent.py` and `services/state_engine.py`.
- **Directories**:
  - `/routers`: Exposes endpoints mapped directly to what Express needs.
  - `/services`: Contains Bayesian Knowledge Tracing logic, Trend Engine rules, Context Retrievers, and Gemini interfaces.
  - `/app/graph`: Houses LangGraph files detailing agentic routing steps, critic nodes, and semester graph analysis workflows.

---

## Database Modeling
The database uses a single unified schema shared between Node and Python.

**Managed by Sequelize (Express)**:
- `Users`: Central authentication profiles.
- `InitialProfile`: Onboarding info (stores JSON objects for preferences, AI prediction values, and activated agents).
- `ChatThread` & `ChatMessage`: Persistent chat interactions.
- `InteractionLog`: Event tracking, sentiment/mood captures, confidence scoring.
- `BktSkillMastery`: Tracks per-skill probabilities (p_init, p_transit, p_guess, etc.) for BKT mapping.
- `StudentProfileState`: Hidden state persistence.
- Progress metrics: `WellnessLog`, `SocialMetrics`, `AcademicProgress`, `StudentInteraction`.

**Managed by SQLAlchemy / FastAPI**:
- `agent_memory`: A real-time cross-agent synchronization table (e.g. Wellness writes mood here, Academic reads it for tone context).
- `student_model_embeddings` / `episodic_memory` / `knowledge_chunks`: `pgvector` tables containing vector columns (Dimension: 1536) used to retrieve scaffolding snippets, past memories, and synthesized profiles natively without recalculation.
- Plans & Analytics: `academic_plans`, `social_plans`, `wellness_plans`, `outcome_reports`. (All vector enabled).

---

## Key Achievements & Technical Merits
1. **Separation of Concerns**: Utilizing a fast Express layer guarantees web requests, auth, and general DB hits don't hang due to expensive AI inferences that take place in the background or stream via Python.
2. **Latent Cognitive Tracking**: The system accurately profiles users not just off static data but off moving behavioral clues—BKT updates with every query, and interaction logs adjust frustration/readiness labels per session.
3. **Cross-Agent Memory**: The unique memory pipeline allows an Academic agent to seamlessly understand a student is frustrated or dealing with anxiety because the Wellness agent synced an emotional state into `agent_memory`. 
4. **Resiliency**: Utilizing modern integrations (like updating to the official Google GenAI SDK for embeddings) and graceful fallbacks ensures no API deprecation permanently brings down the core flow.

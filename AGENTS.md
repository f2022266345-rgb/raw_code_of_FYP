# LUMINA Agents Runbook (Memory-Efficient)

## 1) What This Project Is

- Lumina is a culturally-aware, multi-agent AI tutoring ecosystem for Pakistani university students.
- It combines three intelligence layers:
  - BKT mastery tracking (per-skill probability updates)
  - Cognitive trend detection (struggle/flow/disengagement)
  - LLM response generation (Gemini, state/persona-conditioned)

## 2) Active Stack in This Repo

- Frontend: Next.js app in frontend
- Backend A (API Gateway + Auth + DB business layer): Node/Express in backend-express
- Backend B (AI inference/orchestration): FastAPI in backend-fastapi
- Database: PostgreSQL (with pgvector expected for vector features)

## 3) Current Runtime Flow (Agent Chat)

1. Frontend sends chat message to Express: POST /api/chat
2. Frontend includes current in-memory chat window (recent turns) in the same request.
3. Express authenticates user, fetches recent persisted chat turns from InteractionLog, and forwards both windows to FastAPI: POST /api/agent/chat
4. FastAPI retrieves student context from DB mirrors, optionally performs lightweight routing when agent_type is coordinator/auto, applies agent-specific guardrails, builds the state/persona prompt package, builds a context window (session + DB), generates an AI summary of chat history for continuity, and then calls Gemini with prompt + context window + summary.
5. FastAPI returns response + metadata (state, persona, p_mastery, routed_agent).
6. Express logs user/assistant events and returns final response to frontend.
7. FastAPI runs a background extraction step to update InitialProfile (learning_barriers_score, wellness_support_needed, social_support_needed) based on the latest conversation summary.

## 3.1) Current Runtime Flow (Onboarding)

1. Frontend submits onboarding form to Express: POST /api/initial-profiling
2. Express immediately saves raw onboarding data in InitialProfile:
  - educationalBackground
  - learningPreferences
  - culturalContext
  - diagnosticAssessment
3. Express calls FastAPI ML endpoint: POST /api/predict/initial-profile
4. Express saves prediction outputs in InitialProfile:
  - bloom_level_predicted
  - language_barrier_risk
  - learning_barriers_score
  - wellness_support_needed
  - social_support_needed
  - academic_support_needed
5. Express computes cognitive rules and persists them:
  - pacing
  - chunking
  - languageSupport
6. Express activates agent mappings and persists active_agents
7. Express marks user onboarded and returns dashboard-ready payload

Why this matters:
- Initial profiling is the control layer for personalization.
- It prevents one-size-fits-all tutoring by converting raw form data into support-aware routing (academic/social/wellness), pacing strategy, and language scaffolding.
- It creates a durable baseline used by dashboard, chat orchestration, and future BKT/trend updates.

## 3.2) Current Runtime Flow (Cognitive Understanding)

1. Observable interaction logs are written through chat, observations, and BKT endpoints.
2. Express updates per-skill mastery using BKT with skill identifiers from interaction metadata/content context.
3. Express recomputes trend slopes over the latest 5 to 10 student_interactions:
  - accuracy trend slope
  - time trend slope
  - hint trend slope
4. Express persists the hidden state snapshot in student_profile_state:
  - mastery summary
  - frustration estimate
  - engagement estimate
  - readiness estimate
  - hidden_state mapping JSON
5. The latent-state layer is research-valid because it maps observables to inferred learner states:
  - correctness, hints, response time, session time, sentiment -> frustration / engagement / readiness
  - skill-level evidence -> mastery probability P(Know)

Why this matters:
- These hidden states are not directly observable, so they must be inferred from behavior.
- This gives the tutoring system a structured learner model that can adapt explanations, pacing, and agent routing.

## 4) Key Files (Do Not Break)

- Express entry: backend-express/server.js
- Express chat proxy: backend-express/controllers/chatController.js
- Express onboarding bridge: backend-express/controllers/onboardingControllers.js
- FastAPI entry: backend-fastapi/main.py
- FastAPI router: backend-fastapi/routers/agent_router.py
- FastAPI Gemini adapter: backend-fastapi/services/gemini_agent.py
- Shared frontend API config: frontend/lib/api.ts

## 5) Environment Sync Contract

- Express .env (backend-express/.env):
  - PORT=4000
  - FASTAPI_BASE_URL=<http://localhost:8080> (FastAPI backend on port 8080 due to local port conflict)
  - DATABASE_URL=postgres://...
  - JWT_SECRET=...
- FastAPI .env (backend-fastapi/.env):
  - DATABASE_URL=postgresql+psycopg://... (or normalized equivalent)
  - GITHIB_API_URl=https://models.inference.ai.azure.com (GitHub Models base URL; typo preserved per project)
  - GITHUB_TOKEN=... (GitHub Personal Access Token used as API key)
  - GITHUB_MODEL=gpt-4o-mini (or another available GitHub Models chat model)
  - (optional legacy) GEMINI_API_KEY=... / GEMINI_MODEL=... if you keep Gemini around

Rule: Frontend should call only Express base URL. Express talks to FastAPI via FASTAPI_BASE_URL.

## 6) Frontend API Rule

- Use frontend/lib/api.ts for all frontend network calls.
- Avoid hardcoding localhost ports inside components/pages.
- Preferred usage:
  - buildApiUrl("/api/chat")
  - buildApiUrl("/api/initial-profiling")
  - buildApiUrl("/api/chat/history")
  - buildApiUrl("/api/chat/memories")
- Chat payload contract for POST /api/chat should include:
  - message
  - agentType
  - skillName
  - chatHistory (recent in-session turns, recommended last 12)
- Chat history query contract for GET /api/chat/history supports:
  - q (message search)
  - agent (coordinator|academic|social|wellness)
  - role (user|assistant)
  - date (single day)
  - fromDate / toDate (range)
  - order (asc|desc)
  - limit

## 7) Implementation Status Snapshot

- Done:
  - BKT training + parameter extraction pipeline
  - Initial profiling model (Random Forest, serialized)
  - Trend engine logic
  - Express↔FastAPI onboarding/chat integration
  - Token-optimized Gemini orchestration route
  - Context window continuity (frontend history + DB history merged per request)
  - AI-generated chat-history summary injected into Gemini prompt
  - Looser conversational prompt style (less rigid response constraints)
  - Dashboard Chat History page with backend-driven search + date filters
  - Memory tab with topic-bucketed AI summaries (math, health, family, etc.)
  - Onboarding persistence pipeline enforced: Form -> Save raw -> Predict -> Save predictions -> Compute cognitive rules -> Activate agents -> Dashboard-ready response
- In progress:
  - pgvector-first semantic memory flow hardening
  - full production-grade endpoint integration and deployment readiness
  - post-chat profile update tuning (LLM extraction prompts)

## 8) Known Risks / Notes

- ✅ **FIXED: Gemini Import Error** - Previous code used `from google import genai` which caused "cannot import name 'genai'" error. Corrected to `import google.generativeai as genai` with proper API initialization via `genai.configure(api_key=...)` and `genai.GenerativeModel()`. Real Gemini responses now flow through the pipeline.
- ✅ **FIXED: Port Conflict** - FastAPI now runs on port 8080 (port 8000 was occupied). Updated Express FASTAPI_BASE_URL to <http://localhost:8080>.
- ✅ **FIXED: Truncated/Short Agent Replies** - FastAPI Gemini orchestration now prefers complete responses by default, increased response token budget, and performs a continuation call when generation stops at token limit. This prevents cut-off replies such as partial last sentences.
- Legacy FastAPI file backend/services/chat_service.py still references OpenAI; active agent-chat flow uses gemini_agent.py through /api/agent/chat.
- FastAPI DB init expects vector extension in local PostgreSQL.
- If vector extension is unavailable locally, vector-dependent features may degrade or fail.
- Initial profiling artifacts (`student_model.pkl`, `encoders.pkl`) were trained on older scikit-learn; runtime suppresses `InconsistentVersionWarning` for stability until artifacts are retrained on the current sklearn version.

## 9) Local Run Order

1. Start PostgreSQL and ensure database exists.
2. Start FastAPI backend (port 8080).
3. Start Express backend (port 4000).
4. Start Next.js frontend (port 3000 by default).
5. Verify:
   - Express health: GET /health
   - FastAPI health: GET /health
   - Agent chat path from frontend dashboard chat widget

## 10) Immediate Next Steps

- Validate pgvector extension setup locally or move DB to Neon/Supabase with pgvector enabled.
- Keep frontend API calls centralized in frontend/lib/api.ts.
- Remove/retire stale OpenAI-only service path if no longer needed.
- Retrain and re-export initial profiling model artifacts with the currently pinned scikit-learn version to remove compatibility debt.

## 11) Latest Code Policy

- Treat `backend/routers/agent_router.py` + `backend/services/gemini_agent.py` as the active inference/chat pipeline.
- Keep `AGENTS.md` updated when runtime contracts change (ports, env variables, model IDs, persistence sequence).
- Prefer incremental updates in active files over reviving legacy paths.
- Keep context-window contract stable across layers:
  - Frontend sends chatHistory
  - Express adds database_chat_history
  - FastAPI summarizes + injects continuity context into Gemini prompt
- Academic agent guardrail:
  - If a message is about stress/mental health/social issues, Academic replies with the exact Wellness handoff sentence.
- Response quality policy for active chat pipeline:
  - Do not force ultra-short replies by default.
  - Prefer complete, coherent answers unless the student explicitly requests short output.
  - If Gemini stops due to max token limit, continue generation and merge continuation.
- Keep chat-history and memory endpoints stable:
  - Express /api/chat/history handles date/search/filter queries against InteractionLog
  - Express /api/chat/memories builds topic buckets and requests AI summaries from FastAPI /api/agent/memory/summary

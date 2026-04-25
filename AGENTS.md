# LUMINA Agents Runbook (Memory-Efficient)

## 1) What This Project Is

- Lumina is a culturally-aware, multi-agent AI tutoring ecosystem for Pakistani university students.
- It combines three intelligence layers:
  - BKT mastery tracking (per-skill probability updates)
  - Cognitive trend detection (struggle/flow/disengagement)
  - LLM response generation (Gemini, state/persona-conditioned)

## 2) Active Stack in This Repo

- Frontend: Next.js app in FYP_Project
- Backend A (API Gateway + Auth + DB business layer): Node/Express in backend_express
- Backend B (AI inference/orchestration): FastAPI in backend
- Database: PostgreSQL (with pgvector expected for vector features)

## 3) Current Runtime Flow (Agent Chat)

1. Frontend sends chat message to Express: POST /api/chat
2. Express authenticates user, enriches context, forwards to FastAPI: POST /api/agent/chat
3. FastAPI pipeline runs:
   - Retrieve student context from DB mirrors
   - Build state/persona prompt package
   - Call Gemini with token-optimized instruction
4. FastAPI returns response + metadata (state, persona, p_mastery)
5. Express logs user/assistant events and returns final response to frontend

## 4) Key Files (Do Not Break)

- Express entry: backend_express/server.js
- Express chat proxy: backend_express/controllers/chatController.js
- Express onboarding bridge: backend_express/controllers/onboardingControllers.js
- FastAPI entry: backend/main.py
- FastAPI router: backend/routers/agent_router.py
- FastAPI Gemini adapter: backend/services/gemini_agent.py
- Shared frontend API config: FYP_Project/lib/api.ts

## 5) Environment Sync Contract

- Express .env (backend_express/.env):
  - PORT=4000
  - FASTAPI_BASE_URL=http://localhost:8080 (FastAPI backend on port 8080 due to local port conflict)
  - DATABASE_URL=postgres://...
  - JWT_SECRET=...
- FastAPI .env (backend/.env):
  - DATABASE_URL=postgresql+psycopg://... (or normalized equivalent)
  - GEMINI_API_KEY=... (required for real Gemini API responses)
  - GEMINI_MODEL=gemini-flash-latest (or other available model)

Rule: Frontend should call only Express base URL. Express talks to FastAPI via FASTAPI_BASE_URL.

## 6) Frontend API Rule

- Use FYP_Project/lib/api.ts for all frontend network calls.
- Avoid hardcoding localhost ports inside components/pages.
- Preferred usage:
  - buildApiUrl("/api/chat")
  - buildApiUrl("/api/initial-profiling")

## 7) Implementation Status Snapshot

- Done:
  - BKT training + parameter extraction pipeline
  - Initial profiling model (Random Forest, serialized)
  - Trend engine logic
  - Express↔FastAPI onboarding/chat integration
  - Token-optimized Gemini orchestration route
- In progress:
  - pgvector-first semantic memory flow hardening
  - full production-grade endpoint integration and deployment readiness

## 8) Known Risks / Notes

- ✅ **FIXED: Gemini Import Error** - Previous code used `from google import genai` which caused "cannot import name 'genai'" error. Corrected to `import google.generativeai as genai` with proper API initialization via `genai.configure(api_key=...)` and `genai.GenerativeModel()`. Real Gemini responses now flow through the pipeline.
- ✅ **FIXED: Port Conflict** - FastAPI now runs on port 8080 (port 8000 was occupied). Updated Express FASTAPI_BASE_URL to http://localhost:8080.
- Legacy FastAPI file backend/services/chat_service.py still references OpenAI; active agent-chat flow uses gemini_agent.py through /api/agent/chat.
- FastAPI DB init expects vector extension in local PostgreSQL.
- If vector extension is unavailable locally, vector-dependent features may degrade or fail.
- Initial profiling artifacts (`student_model.pkl`, `encoders.pkl`) were trained on older scikit-learn; runtime suppresses `InconsistentVersionWarning` for stability until artifacts are retrained on the current sklearn version.

## 9) Local Run Order

1. Start PostgreSQL and ensure database exists.
2. Start FastAPI backend (port 8000).
3. Start Express backend (port 4000).
4. Start Next.js frontend (port 3000 by default).
5. Verify:
   - Express health: GET /health
   - FastAPI health: GET /health
   - Agent chat path from frontend dashboard chat widget

## 10) Immediate Next Steps

- Validate pgvector extension setup locally or move DB to Neon/Supabase with pgvector enabled.
- Keep frontend API calls centralized in FYP_Project/lib/api.ts.
- Remove/retire stale OpenAI-only service path if no longer needed.
- Retrain and re-export initial profiling model artifacts with the currently pinned scikit-learn version to remove compatibility debt.

## 11) Latest Code Policy

- Treat `backend/routers/agent_router.py` + `backend/services/gemini_agent.py` as the active inference/chat pipeline.
- Keep `AGENTS.md` updated when runtime contracts change (ports, env variables, model IDs, persistence sequence).
- Prefer incremental updates in active files over reviving legacy paths.

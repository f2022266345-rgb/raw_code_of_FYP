# LUMINA Agents Runbook (Memory-Efficient)

## 1) What This Project Is

- Lumina is a culturally-aware, multi-agent AI tutoring ecosystem for Pakistani university students.
- It combines three intelligence layers:
  - BKT mastery tracking (per-skill probability updates)
  - Cognitive trend detection (struggle/flow/disengagement)
  - LLM response generation (Groq, multi-model split: router/reasoning/chat, state/persona-conditioned)

## 2) Active Stack in This Repo

- Frontend: Next.js app in frontend
- Backend A (API Gateway + Auth + DB business layer): Node/Express in backend-express
- Backend B (AI inference/orchestration): FastAPI in backend-fastapi
- Database: PostgreSQL (with pgvector expected for vector features)

## 3) Current Runtime Flow (Agent Chat)

1. Frontend sends chat message to Express: POST /api/chat
2. Frontend includes current in-memory chat window (recent turns) in the same request.
3. Express authenticates user via Clerk, fetches recent persisted chat turns, and forwards both windows to FastAPI: POST /api/agent/chat
4. FastAPI retrieves a comprehensive 6-table student context (BKT mastery, InitialProfile, InteractionLog, AgentMemory, StudentModelEmbedding, EpisodicMemory). It optionally performs lightweight routing when agent_type is coordinator/auto, applies agent-specific guardrails, builds the state/persona prompt package, builds a context window (session + DB) of prior turns as role/content messages, and then calls the Groq CHAT model (qwen) with system prompt + history + current message. Header "action" buttons (academic plan / wellness report / social plan) instead call the Groq REASONING model over the full student context and return structured JSON.
5. FastAPI returns response + metadata (state, persona, p_mastery, routed_agent).
6. Express logs user/assistant events and returns final response to frontend.
7. FastAPI runs a background extraction step to update InitialProfile (learning_barriers_score, wellness_support_needed, social_support_needed) and synthesize EpisodicMemory based on the latest conversation summary.

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
- FastAPI entry: backend/main.py
- FastAPI router: backend/routers/agent_router.py
- FastAPI LLM layer (Groq): backend/services/agent_llm.py
- FastAPI Groq client (3 role models): backend/services/groq_client.py
- FastAPI Jina embeddings: backend/services/jina_embeddings.py
- FastAPI agent router-model: backend/services/router_agent.py
- FastAPI deep-report context: backend/services/user_context.py
- Express deep-report proxies: backend-express/controllers/agentController.js
- Express right-rail feeds: backend-express/controllers/feedController.js
- Shared frontend API config: FYP_Project/lib/api.ts

## 5) Environment Sync Contract

- Express .env (backend-express/.env):
  - PORT=4000
  - FASTAPI_BASE_URL=<http://localhost:8000> (FastAPI backend)
  - DATABASE_URL=postgres://...
  - JWT_SECRET=...
  - NEWS_API_KEY= / GOOGLE_PLACES_API_KEY= (optional right-rail feed providers; empty = card hides)
- FastAPI .env (backend/.env):
  - DATABASE_URL=postgresql+psycopg://... (or normalized equivalent)
  - **Groq (chat/reasoning/routing)** — confirm live models at <https://console.groq.com/docs/models>:
    - GROQ_API_KEY=... / GROQ_BASE_URL=https://api.groq.com/openai/v1 (the Groq SDK appends /openai/v1 itself — the client strips a duplicate)
    - GROQ_MODEL_ROUTER=openai/gpt-oss-20b (effort=low) — function-calling / agent routing
    - GROQ_MODEL_REASONING=openai/gpt-oss-120b (effort=high, JSON) — deep plans/reports; effort=medium (GROQ_MEDIUM_EFFORT) for LangGraph plan/analysis nodes
    - GROQ_MODEL_CHAT=llama-3.3-70b-versatile — persona conversation (non-reasoning → fast, no thinking tokens; reasoning models are sent reasoning_format=hidden)
  - **Gemini embeddings (pgvector)**:
    - GEMINI_API_KEY=... (Google AI Studio) / GEMINI_EMBED_MODEL=gemini-embedding-001
    - GEMINI_EMBED_DIM=1024 — output_dimensionality, L2-normalized in code; MUST equal the pgvector column dim (see migrations/007_jina_embeddings_1024.sql). task_type RETRIEVAL_DOCUMENT (write) / RETRIEVAL_QUERY (read).

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
  - Token-optimized Groq (CHAT model) orchestration route
  - Context window continuity (frontend history + DB history merged per request)
  - Multi-model split: Groq router/reasoning/chat sharing one Jina-embedded pgvector memory
  - Deep-report endpoints (academic plan / wellness report / social plan) + Express proxies + right-rail feeds
  - Looser conversational prompt style (less rigid response constraints)
  - Dashboard Chat History page with backend-driven search + date filters
  - Memory tab with topic-bucketed AI summaries (math, health, family, etc.)
  - Onboarding persistence pipeline enforced: Form -> Save raw -> Predict -> Save predictions -> Compute cognitive rules -> Activate agents -> Dashboard-ready response
- In progress:
  - pgvector-first semantic memory flow hardening
  - full production-grade endpoint integration and deployment readiness
  - post-chat profile update tuning (LLM extraction prompts)
  - LangGraph workflows for multi-agent streaming and semester analysis (currently experimental)

## 8) Known Risks / Notes

- ✅ **Groq multi-model split** - All chat/reasoning/routing go through `services/groq_client.py`: `route()` (gpt-oss-20b, effort low, tool-calling), `reason()` (gpt-oss-120b, effort high/medium, JSON), `chat()` (llama-3.3-70b-versatile, non-reasoning persona). `_supports_reasoning()` gates `reasoning_format`/`reasoning_effort` so Llama isn't sent reasoning params; a one-shot retry drops them on any model that rejects them. `services/agent_llm.py` is the drop-in replacement for the old `gemini_agent.py` (same public API). Confirm live model strings at <https://console.groq.com/docs/models> before deploy.
- ✅ **Agents answer-first** - System prompt rule 8b + the offline fallbacks forbid replying with a question / asking the student to clarify; agents make reasonable assumptions and answer. The academic-plan subject is optional (blank → plan across the student's courses), so no UI ever blocks on input.
- ✅ **Every agent window** has a header action button + live right-rail feed + a "Saved plans & reports" card list (`app/dashboard/agent/[type]/page.tsx`); coordinator/tutor fall back to the academic plan + education feed. Generated plans/reports are stored full-JSON in the `agent_reports` table (FastAPI-managed) and listed as cards; clicking a card opens the whole report via `ReportRenderer`. Endpoints: FastAPI `GET /api/agent/reports/{user_id}?agent=` + `GET /api/agent/report/{user_id}/{id}`, proxied by Express `GET /api/agent/reports` + `/api/agent/report/:id`.
- ✅ **Free-tier token budget** - The deep-report endpoints use `reason()` at **medium** effort with a compacted context (`_compact_ctx`) and modest `max_tokens` (≈2800-3200) to stay under Groq free tier's 8000 tokens/minute. `_reason_json` retries smaller on 413/429 and retries plain-mode on `json_validate_failed`. Bump model tier / `GROQ_REASONING_EFFORT` if on a paid Groq plan.
- ✅ **Gemini embeddings** - Semantic memory uses `services/gemini_embeddings.py` (gemini-embedding-001 @ output_dimensionality=1024, **L2-normalized in code** since gemini-embedding-001 only auto-normalizes 3072 dims; asymmetric RETRIEVAL_DOCUMENT/RETRIEVAL_QUERY tasks). `db.EMBEDDING_DIM` is driven by `GEMINI_EMBED_DIM`. Existing DBs must run `migrations/007_jina_embeddings_1024.sql` then `scripts/reembed.py`. (Jina was removed.)
- ✅ **FIXED: LangGraph LLM path** - `app/graph/nodes/*.py` and `semester_graph.py` now call `groq_client.complete()` (no more removed-Gemini-client crash).
- ✅ **FIXED: Context Truncation Bug** - `_truncate_to_token_limit` in `agent_llm.py` now uses the chars/4 heuristic instead of word count.
- ✅ **FIXED: Truncated/Short Agent Replies** - The CHAT-model turn prefers complete responses, raises the token budget, and performs a continuation call when generation hits the length limit.
- Port: FastAPI runs on 8000 (Express `FASTAPI_BASE_URL=http://localhost:8000`).
- Legacy FastAPI file backend/services/chat_service.py still references OpenAI; active agent-chat flow uses `agent_llm.py` through /api/agent/chat.
- FastAPI DB init expects the `vector` extension in PostgreSQL; vector-dependent features degrade if unavailable.
- Initial profiling artifacts (`student_model.pkl`, `encoders.pkl`) were trained on older scikit-learn; runtime suppresses `InconsistentVersionWarning` until retrained.
- ⚠️ **DB Sync Risk**: Express `server.js` uses manual migrations (auto-sync disabled). Run `npm run db:migrate` for schema changes.

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

- Treat `backend/routers/agent_router.py` + `backend/services/agent_llm.py` + `backend/services/groq_client.py` as the active inference/chat pipeline.
- Keep `AGENTS.md` updated when runtime contracts change (ports, env variables, model IDs, persistence sequence).
- Prefer incremental updates in active files over reviving legacy paths.
- Keep context-window contract stable across layers:
  - Frontend sends chatHistory
  - Express adds database_chat_history
  - FastAPI merges history into role/content messages for the Groq CHAT model
- Academic agent guardrail:
  - If a message is about stress/mental health/social issues, Academic replies with the exact Wellness handoff sentence.
- Response quality policy for active chat pipeline:
  - Do not force ultra-short replies by default.
  - Prefer complete, coherent answers unless the student explicitly requests short output.
  - If the model stops due to max token limit, continue generation and merge continuation.
- Keep chat-history and memory endpoints stable:
  - Express /api/chat/history handles date/search/filter queries against InteractionLog
  - Express /api/chat/memories builds topic buckets and requests AI summaries from FastAPI /api/agent/memory/summary

# LUMINA — Multi-Model Upgrade Implementation Spec

> Hand this file to your coding agent (Claude Code / Cursor / Cowork) **or** follow it yourself.
> It is written as an executable runbook: every section has exact file paths, env keys, and code.
> Place this file at the repo root as `LUMINA_UPGRADE_SPEC.md` so the agent can read it.

---

## 0. Goal of this upgrade

Four changes to the existing LUMINA stack (Next.js + Express:4000 + FastAPI:8080 + Postgres/pgvector):

1. **Replace Gemini with Groq** everywhere in the backend (Groq is OpenAI-compatible, so it's a base-URL + key swap plus a thin client).
2. **Use Jina AI for embeddings** (semantic memory / pgvector) instead of whatever embedding path exists now.
3. **Split work across multiple Groq models by task** — a router model, a reasoning model, and a chat/persona model — so each job runs on the cheapest model that can do it well, and they share the same vector memory.
4. **Add frontend actions + right-side real-time panels**:
   - Academic agent → "Plan your academic activity" button (asks subject, then reasons over full user data).
   - Wellness agent → "Determine your health" button (full wellness report over user data).
   - Social agent → "Plan your social activity" button.
   - Chat stays conversational, personalized with user history.
   - Right rail per agent: live news / LinkedIn / doctor-finder cards relevant to that agent.

---

## 1. IMPORTANT — model names changed (read before coding)

The model names you listed are conceptually right, but two were **deprecated on Groq (June 17, 2026)**. Use the live replacements below. Keep the *role* mapping; only the string changes. Put every model string in `.env` so you can swap later without touching code.

| Your intended role | You named | Live Groq model to use | Groq deprecation note |
|---|---|---|---|
| Router / tool-use (Manager) | Llama 4 Scout / Qwen3 27B | `openai/gpt-oss-120b` *(or `qwen/qwen3.6-27b`)* | Llama 4 Scout deprecated → migrate to gpt-oss-120b or qwen3.6-27b |
| Reasoning (Lesson Planner) | GPT-OSS 120B | `openai/gpt-oss-120b` | current, flagship reasoning |
| Persona / chat (Friendly Tutor) | Llama 3.3 70B | `qwen/qwen3.6-27b` *(or `openai/gpt-oss-20b` for speed)* | Llama 3.3 70B deprecated → migrate to qwen3.6-27b or gpt-oss-120b |

> If you have an **enterprise committed-spend** Groq contract, the old `llama-3.3-70b-versatile` / `llama-4-scout-17b-16e-instruct` strings still resolve. For free/developer tier they will fail — that is why this spec uses the replacements. **Always confirm the live list at `https://console.groq.com/docs/models` before deploy** — Groq's catalog churns.

Recommended default split (good cost/quality balance, all currently live):
- `GROQ_MODEL_ROUTER=openai/gpt-oss-120b` with `reasoning_effort=low` (fast tool routing)
- `GROQ_MODEL_REASONING=openai/gpt-oss-120b` with `reasoning_effort=high` (deep planning)
- `GROQ_MODEL_CHAT=qwen/qwen3.6-27b` (natural conversation, instruction-following)

### Embedding model note (affects your DB schema)
- `jina-embeddings-v5-text-small` → **1024 dimensions**, 32K context, 119+ languages.
- `jina-embeddings-v5-text-nano` → **768 dimensions** (cheaper/edge).
- Use `task: "retrieval.passage"` when embedding stored memories, `task: "retrieval.query"` when embedding the incoming query (asymmetric retrieval). `normalized: true` so you can use cosine/inner-product directly.
- **If your `pgvector` column was created for a different dimension (e.g. Gemini's 768 or OpenAI's 1536), you MUST recreate the column at the Jina dimension and re-embed existing rows.** See §4.3.

---

## 2. Environment variables (`.env`)

Add these. You will paste the real keys. **Never commit `.env`.**

### `backend-fastapi/.env`
```dotenv
# --- Groq (replaces Gemini) ---
GROQ_API_KEY=                       # paste your Groq key
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL_ROUTER=openai/gpt-oss-120b
GROQ_MODEL_REASONING=openai/gpt-oss-120b
GROQ_MODEL_CHAT=qwen/qwen3.6-27b
GROQ_ROUTER_EFFORT=low
GROQ_REASONING_EFFORT=high
GROQ_REQUEST_TIMEOUT=60

# --- Jina embeddings ---
JINA_API_KEY=                       # paste your Jina key
JINA_BASE_URL=https://api.jina.ai/v1/embeddings
JINA_EMBED_MODEL=jina-embeddings-v5-text-small
JINA_EMBED_DIM=1024                 # MUST match pgvector column + JINA_EMBED_MODEL

# --- existing ---
DATABASE_URL=postgresql+psycopg://...
```

### `backend-express/.env`
```dotenv
PORT=4000
FASTAPI_BASE_URL=http://localhost:8080
DATABASE_URL=postgres://...
JWT_SECRET=...
FRONTEND_URL=http://localhost:3000
# Real-time right-rail feed keys (optional, used by §6)
NEWS_API_KEY=
# any third-party feed keys go here
```

> Delete all `GEMINI_API_KEY`, `GEMINI_MODEL` references after migration (§3.5).

---

## 3. Backend part A — Groq client + model-split service (FastAPI)

### 3.1 Install
```bash
cd backend-fastapi
pip install groq httpx --break-system-packages
# (groq SDK is OpenAI-compatible; httpx for the Jina REST call)
```

### 3.2 New file: `backend-fastapi/services/groq_client.py`
Single source of truth for all LLM calls. Three helper functions, one per role.

```python
import os
from groq import Groq

_client = Groq(
    api_key=os.environ["GROQ_API_KEY"],
    base_url=os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
)

ROUTER_MODEL    = os.environ["GROQ_MODEL_ROUTER"]
REASONING_MODEL = os.environ["GROQ_MODEL_REASONING"]
CHAT_MODEL      = os.environ["GROQ_MODEL_CHAT"]
ROUTER_EFFORT   = os.environ.get("GROQ_ROUTER_EFFORT", "low")
REASONING_EFFORT = os.environ.get("GROQ_REASONING_EFFORT", "high")


def _chat(model, messages, max_tokens=1024, temperature=0.7,
          reasoning_effort=None, response_format=None, tools=None):
    kwargs = dict(model=model, messages=messages,
                  max_tokens=max_tokens, temperature=temperature)
    # reasoning_effort only valid for gpt-oss / reasoning models
    if reasoning_effort and model.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = reasoning_effort
    if response_format:
        kwargs["response_format"] = response_format
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    resp = _client.chat.completions.create(**kwargs)
    return resp


# ---- ROLE 1: ROUTER (manager / tool-use) ----
def route(messages, tools=None):
    """Fast classification + tool routing. Low reasoning effort."""
    return _chat(ROUTER_MODEL, messages, max_tokens=512, temperature=0.2,
                 reasoning_effort=ROUTER_EFFORT, tools=tools)


# ---- ROLE 2: REASONING (lesson planner / report builder) ----
def reason(messages, json_mode=True, max_tokens=4096):
    """Deep reasoning for plans/reports. High reasoning effort. JSON out."""
    rf = {"type": "json_object"} if json_mode else None
    return _chat(REASONING_MODEL, messages, max_tokens=max_tokens,
                 temperature=0.4, reasoning_effort=REASONING_EFFORT,
                 response_format=rf)


# ---- ROLE 3: CHAT (friendly persona tutor) ----
def chat(messages, max_tokens=1024):
    """Natural conversation, instruction-following, personalized."""
    return _chat(CHAT_MODEL, messages, max_tokens=max_tokens, temperature=0.8)


def text_of(resp):
    return resp.choices[0].message.content or ""
```

### 3.3 Replace Gemini call sites
Old active path was `services/gemini_agent.py` via `/api/agent/chat`. Migrate it:

```python
# backend-fastapi/services/gemini_agent.py  (rename mentally to "agent_llm")
from .groq_client import chat, reason, route, text_of

# OLD:
#   from google import genai
#   client = genai.Client(api_key=...)
#   resp = client.models.generate_content(model=GEMINI_MODEL, contents=...)
#   return resp.text

# NEW (conversation turn) — use the CHAT model:
def generate_agent_reply(system_prompt, context_window, summary, user_msg):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"Conversation summary so far:\n{summary}"},
        *context_window,                       # prior turns as role/content dicts
        {"role": "user", "content": user_msg},
    ]
    resp = chat(messages, max_tokens=1024)
    return text_of(resp)
```

> **Fix the token bug while you're here** (from the previous plan): `_truncate_to_token_limit` must use chars/4, not word count. Or call Groq's tokenizer. Don't ship the word-count version.

### 3.4 New file: `backend-fastapi/services/router_agent.py`
The "active agent" that decides which sub-agent/tool handles a message, using the ROUTER model with tool-calling.

```python
import json
from .groq_client import route, text_of

ROUTING_TOOLS = [
    {"type": "function", "function": {
        "name": "select_agent",
        "description": "Pick which specialist handles this student message.",
        "parameters": {"type": "object", "properties": {
            "agent": {"type": "string",
                      "enum": ["academic", "wellness", "social", "coordinator"]},
            "skill_name": {"type": "string"},
            "reason": {"type": "string"}
        }, "required": ["agent"]}
    }}
]

def select_agent(user_msg, recent_turns):
    messages = [
        {"role": "system", "content":
         "You route a Pakistani first-semester student's message to the right "
         "specialist agent. academic=study help, wellness=stress/mental health, "
         "social=loneliness/peer/club, coordinator=anything else or mixed."},
        *recent_turns,
        {"role": "user", "content": user_msg},
    ]
    resp = route(messages, tools=ROUTING_TOOLS)
    tc = resp.choices[0].message.tool_calls
    if tc:
        args = json.loads(tc[0].function.arguments)
        return args.get("agent", "coordinator"), args.get("skill_name")
    return "coordinator", None
```

### 3.5 Cleanup
- Delete `GEMINI_API_KEY` / `GEMINI_MODEL` from both `.env` files.
- `grep -r "genai" backend-fastapi/` and `grep -r "gemini" backend-fastapi/` — replace every hit with the `groq_client` helpers.
- Remove the dead `services/chat_service.py` OpenAI references.
- Update `AGENTS.md` §5 and §8: model IDs are now Groq, not Gemini.

---

## 4. Backend part B — Jina embeddings + pgvector

### 4.1 New file: `backend-fastapi/services/jina_embeddings.py`
```python
import os, httpx

JINA_URL   = os.environ.get("JINA_BASE_URL", "https://api.jina.ai/v1/embeddings")
JINA_KEY   = os.environ["JINA_API_KEY"]
JINA_MODEL = os.environ.get("JINA_EMBED_MODEL", "jina-embeddings-v5-text-small")
JINA_DIM   = int(os.environ.get("JINA_EMBED_DIM", "1024"))

_headers = {"Authorization": f"Bearer {JINA_KEY}", "Content-Type": "application/json"}

async def embed(texts: list[str], task: str = "retrieval.passage") -> list[list[float]]:
    """task: 'retrieval.passage' for stored memories, 'retrieval.query' for queries."""
    payload = {
        "model": JINA_MODEL,
        "task": task,
        "normalized": True,
        "input": [{"text": t} for t in texts],
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(JINA_URL, headers=_headers, json=payload)
        r.raise_for_status()
        data = r.json()["data"]
    return [d["embedding"] for d in data]

async def embed_one(text: str, task: str = "retrieval.passage") -> list[float]:
    return (await embed([text], task))[0]
```

### 4.2 Embed on write, query on read
- When you synthesize an `EpisodicMemory` / `StudentModelEmbedding` row, call `embed_one(summary, task="retrieval.passage")` and store the vector.
- When you retrieve relevant memory for a chat turn, call `embed_one(user_msg, task="retrieval.query")` and do a pgvector cosine search.

### 4.3 Migration — fix the vector dimension
> Required if your existing vector column is NOT 1024. Skipping this = silent dimension-mismatch errors on insert.

```sql
-- backend-fastapi migration (run once)
-- 1. Add new correctly-sized column
ALTER TABLE student_model_embeddings ADD COLUMN embedding_v5 vector(1024);
ALTER TABLE episodic_memory          ADD COLUMN embedding_v5 vector(1024);

-- 2. (Re-embed existing rows in a one-off script — see below, then:)
-- 3. Drop old column, rename new one
ALTER TABLE student_model_embeddings DROP COLUMN embedding;
ALTER TABLE student_model_embeddings RENAME COLUMN embedding_v5 TO embedding;
ALTER TABLE episodic_memory          DROP COLUMN embedding;
ALTER TABLE episodic_memory          RENAME COLUMN embedding_v5 TO embedding;

-- 4. Recreate the index for the new dim
CREATE INDEX ON student_model_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON episodic_memory          USING hnsw (embedding vector_cosine_ops);
```

One-off re-embed script (`backend-fastapi/scripts/reembed.py`):
```python
import asyncio
from services.jina_embeddings import embed_one
# pseudo: for each row with old text summary -> embedding_v5 = await embed_one(summary)
# UPDATE ... SET embedding_v5 = :vec WHERE id = :id
```

### 4.4 Retrieval query (pgvector cosine)
```sql
SELECT summary, 1 - (embedding <=> :query_vec) AS score
FROM episodic_memory
WHERE user_id = :user_id
ORDER BY embedding <=> :query_vec
LIMIT 5;
```

---

## 5. Backend part C — the three new "full report" endpoints

These power the frontend buttons. All three: **load the student's full profile + history, send it to the REASONING model, return structured JSON.** Each also writes a memory row (embedded via Jina) so the active agent shares it.

### 5.1 Shared helper — gather full user context
`backend-fastapi/services/user_context.py`
```python
async def gather_full_context(user_id, db) -> dict:
    """One bundle the reasoning model gets for any deep task."""
    return {
        "profile": await get_initial_profile(user_id, db),     # bloom level, risks, prefs, cultural
        "mastery": await get_bkt_mastery(user_id, db),         # per-skill P(Know)
        "trends": await get_trend_state(user_id, db),          # frustration/engagement/readiness
        "recent_interactions": await get_recent_interactions(user_id, db, limit=30),
        "memories": await get_topic_memories(user_id, db),     # academic/health/social buckets
    }
```

### 5.2 Academic plan — `POST /api/agent/academic/plan`
Body: `{ user_id, subject, goal? }`
```python
from .groq_client import reason, text_of
from .user_context import gather_full_context
from .jina_embeddings import embed_one
import json

@router.post("/api/agent/academic/plan")
async def academic_plan(payload: dict, db=Depends(get_db)):
    ctx = await gather_full_context(payload["user_id"], db)
    prompt = f"""You are an academic planning agent for a Pakistani first-semester
university student. Build a structured, Bloom's-Taxonomy-aligned study plan
for the subject: "{payload['subject']}".

STUDENT CONTEXT (use all of it):
{json.dumps(ctx, default=str)}

Return ONLY JSON:
{{
 "subject": str,
 "current_bloom_level": str,
 "diagnosis": str,                       // weak areas from BKT mastery
 "weekly_plan": [
   {{"week": int, "theme": str, "bloom_focus": str,
     "daily_tasks": [{{"day": str, "task": str, "minutes": int}}],
     "milestone": str}}
 ],
 "resources": [{{"title": str, "type": str, "why": str}}],
 "cultural_notes": str                   // language scaffolding if language_barrier_risk high
}}"""
    resp = reason([{"role": "user", "content": prompt}], json_mode=True, max_tokens=4096)
    plan = json.loads(text_of(resp))
    # persist + embed for shared memory
    vec = await embed_one(f"Academic plan for {payload['subject']}: {plan.get('diagnosis','')}")
    await save_plan_and_memory(payload["user_id"], "academic", plan, vec, db)
    return plan
```

### 5.3 Wellness report — `POST /api/agent/wellness/report`
Same shape, REASONING model, prompt asks for a full wellness assessment.
```python
@router.post("/api/agent/wellness/report")
async def wellness_report(payload: dict, db=Depends(get_db)):
    ctx = await gather_full_context(payload["user_id"], db)
    prompt = f"""You are a wellness assessment agent. Produce a supportive, NON-clinical
wellbeing report for this first-semester student. Do NOT diagnose. Flag if
professional human support seems warranted.

STUDENT CONTEXT:
{json.dumps(ctx, default=str)}

Return ONLY JSON:
{{
 "overall_summary": str,
 "stress_indicators": [str],
 "engagement_trend": str,
 "strengths": [str],
 "gentle_recommendations": [{{"area": str, "suggestion": str}}],
 "needs_human_support": bool,
 "escalation_reason": str|null
}}"""
    resp = reason([{"role": "user", "content": prompt}], json_mode=True, max_tokens=3072)
    report = json.loads(text_of(resp))
    if report.get("needs_human_support"):
        await flag_escalation(payload["user_id"], report.get("escalation_reason"), db)
    vec = await embed_one("Wellness report: " + report.get("overall_summary", ""))
    await save_plan_and_memory(payload["user_id"], "wellness", report, vec, db)
    return report
```
> **Safety:** the wellness prompt must never output crisis instructions or methods. If `needs_human_support` is true, route to a human and show the student real support resources — do not let the AI handle a crisis alone.

### 5.4 Social plan — `POST /api/agent/social/plan`
```python
@router.post("/api/agent/social/plan")
async def social_plan(payload: dict, db=Depends(get_db)):
    ctx = await gather_full_context(payload["user_id"], db)
    prompt = f"""You are a social integration agent for a Pakistani first-semester
student. Build a plan to improve campus belonging and peer connection.

STUDENT CONTEXT:
{json.dumps(ctx, default=str)}

Return ONLY JSON:
{{
 "summary": str,
 "social_goals": [str],
 "club_recommendations": [{{"name": str, "why": str}}],
 "peer_connection_steps": [{{"step": str, "this_week": bool}}],
 "check_in_schedule": str
}}"""
    resp = reason([{"role": "user", "content": prompt}], json_mode=True, max_tokens=3072)
    plan = json.loads(text_of(resp))
    vec = await embed_one("Social plan: " + plan.get("summary", ""))
    await save_plan_and_memory(payload["user_id"], "social", plan, vec, db)
    return plan
```

### 5.5 Express proxy routes
Frontend calls Express only. Add thin proxies in `backend-express/controllers/agentController.js`:
```javascript
const proxy = (path) => async (req, res) => {
  try {
    const r = await axios.post(`${process.env.FASTAPI_BASE_URL}${path}`,
      { ...req.body, user_id: req.user.id });
    res.json(r.data);
  } catch (e) { res.status(500).json({ error: e.message }); }
};
router.post('/api/academic/plan',  requireAuth, proxy('/api/agent/academic/plan'));
router.post('/api/wellness/report', requireAuth, proxy('/api/agent/wellness/report'));
router.post('/api/social/plan',     requireAuth, proxy('/api/agent/social/plan'));
```
Register them in `frontend/lib/api.ts`: `buildApiUrl('/api/academic/plan')`, etc.

---

## 6. Backend part D — right-rail real-time feeds

One Express endpoint per agent type returns 3–5 live cards. Cache 15 min to respect rate limits.
`backend-express/controllers/feedController.js`
```javascript
// GET /api/feed/:agent   -> agent in {academic, wellness, social}
router.get('/api/feed/:agent', requireAuth, async (req, res) => {
  const { agent } = req.params;
  const cached = feedCache.get(agent);
  if (cached) return res.json(cached);

  let items = [];
  if (agent === 'academic') {
    items = await fetchNews('education technology Pakistan students'); // NEWS_API_KEY
  } else if (agent === 'social') {
    items = await fetchLinkedInOrEvents('student events Lahore campus');
  } else if (agent === 'wellness') {
    items = await fetchDoctors('counselor psychologist Lahore'); // directory/Places API
  }
  const payload = { agent, items: items.slice(0, 5), fetched_at: Date.now() };
  feedCache.set(agent, payload, 15 * 60 * 1000);
  res.json(payload);
});
```
> Use whatever providers you have keys for (NewsAPI, a places/doctor directory, an events API). Keep all keys in `backend-express/.env`. If a feed has no key, return `[]` gracefully — the rail just hides that card.

---

## 7. Frontend — buttons + panels (Next.js)

All calls go through `frontend/lib/api.ts`. No hardcoded ports.

### 7.1 Agent window layout
Two-column: chat (left, flex) + right rail (fixed ~320px).
```
frontend/components/agent/AgentWorkspace.tsx
  ├─ AgentHeader        (title + the action button for this agent)
  ├─ ChatThread         (existing chat, uses CHAT model)
  └─ RightRail          (live feed cards for this agent)
```

### 7.2 Action button per agent (header)
```tsx
// AgentHeader.tsx — renders the right button based on agent type
function AgentHeader({ agent }: { agent: 'academic'|'wellness'|'social' }) {
  const [open, setOpen] = useState(false);
  const labels = {
    academic: 'Plan your academic activity',
    wellness: 'Determine your health',
    social:   'Plan your social activity',
  };
  return (
    <div className="flex items-center justify-between p-4 border-b">
      <h2 className="text-lg font-medium">{titleFor(agent)}</h2>
      <button onClick={() => setOpen(true)} className="btn-primary">
        {labels[agent]}
      </button>
      {open && <ActionModal agent={agent} onClose={() => setOpen(false)} />}
    </div>
  );
}
```

### 7.3 Academic asks for subject first
```tsx
// ActionModal.tsx
function ActionModal({ agent, onClose }) {
  const [subject, setSubject] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    let data;
    if (agent === 'academic') {
      data = await postJSON(buildApiUrl('/api/academic/plan'), { subject });
    } else if (agent === 'wellness') {
      data = await postJSON(buildApiUrl('/api/wellness/report'), {});
    } else {
      data = await postJSON(buildApiUrl('/api/social/plan'), {});
    }
    setResult(data); setLoading(false);
  }

  return (
    <Modal onClose={onClose}>
      {agent === 'academic' && !result && (
        <>
          <label>Which subject do you want a study plan for?</label>
          <input value={subject} onChange={e => setSubject(e.target.value)}
                 placeholder="e.g. Calculus, English Composition" />
          <button disabled={!subject || loading} onClick={run}>
            {loading ? 'Building plan…' : 'Generate plan'}
          </button>
        </>
      )}
      {agent !== 'academic' && !result && (
        <button disabled={loading} onClick={run}>
          {loading ? 'Analyzing your data…' : 'Generate report'}
        </button>
      )}
      {result && <ReportRenderer agent={agent} data={result} />}
    </Modal>
  );
}
```
> `ReportRenderer` just maps the JSON (weekly_plan / recommendations / etc.) into cards. The backend always returns structured JSON, so rendering is deterministic.

### 7.4 Chat stays on the CHAT model
The existing `/api/chat` path already merges session + DB history. No change except: server-side it now calls `chat()` (Qwen) instead of Gemini, and before generating it retrieves top-5 Jina memories and injects them as a system message for personalization.

### 7.5 Right rail
```tsx
function RightRail({ agent }) {
  const [feed, setFeed] = useState([]);
  useEffect(() => {
    fetch(buildApiUrl(`/api/feed/${agent}`)).then(r => r.json())
      .then(d => setFeed(d.items));
  }, [agent]);
  return (
    <aside className="w-80 border-l p-4 space-y-3 overflow-y-auto">
      <h3 className="text-sm font-medium text-gray-500">
        {agent === 'academic' ? 'Latest in education'
         : agent === 'social' ? 'Campus & networking'
         : 'Find support nearby'}
      </h3>
      {feed.map((it, i) => <FeedCard key={i} item={it} />)}
    </aside>
  );
}
```

---

## 8. How the split + shared memory fits together

```
Student message
   │
   ▼
ROUTER model (gpt-oss-120b, effort=low)  ──► picks agent (academic/wellness/social/coordinator)
   │
   ├── button action? ─► REASONING model (gpt-oss-120b, effort=high) ─► structured plan/report (JSON)
   │                                                   │
   │                                                   └─► Jina embed ─► pgvector (shared memory)
   │
   └── normal chat? ─► retrieve top-5 Jina memories ─► CHAT model (qwen3.6-27b) ─► personalized reply
                                                          │
                                                          └─► Jina embed turn ─► pgvector
```
Every model writes to the **same** Jina-embedded pgvector store, so the chat tutor "remembers" what the planner produced, and the planner sees what the student said in chat. That shared vector memory is what makes the active agent feel coherent across the split.

---

## 9. Build order (do in this order)

1. **§2** add env keys (both `.env` files). Confirm Groq + Jina keys work with a curl test.
2. **§3.2–3.3** `groq_client.py` + migrate the chat path off Gemini. Test one chat turn end-to-end.
3. **§4** `jina_embeddings.py` + the pgvector dimension migration (§4.3). Re-embed existing rows.
4. **§5** the three report endpoints + Express proxies.
5. **§7** frontend buttons, modal, ReportRenderer.
6. **§6 + §7.5** real-time feeds + right rail.
7. **§3.5** delete all Gemini code, update `AGENTS.md`.

---

## 10. Verification checklist

- [ ] `curl` to Groq with each of the 3 model strings returns 200 (no deprecated-model error).
- [ ] `curl` to Jina returns 1024-length vectors; `JINA_EMBED_DIM` matches the pgvector column.
- [ ] Chat turn uses CHAT model and injects retrieved memories.
- [ ] Academic button asks subject, returns weekly Bloom-aligned plan, persists a memory row.
- [ ] Wellness button returns report; `needs_human_support=true` triggers escalation, never crisis instructions.
- [ ] Social button returns plan.
- [ ] Right rail loads ≥1 live card per agent (or hides gracefully if no key).
- [ ] No `genai` / `gemini` references remain (`grep` clean).
- [ ] `AGENTS.md` §5/§8 updated to Groq model IDs.

---

## 11. One-paragraph prompt (if you'd rather paste into a coding agent)

> "Migrate the LUMINA FastAPI+Express+Next.js repo from Gemini to Groq (OpenAI-compatible, base URL `https://api.groq.com/openai/v1`, key `GROQ_API_KEY`). Create `services/groq_client.py` exposing three role helpers — `route()` on `GROQ_MODEL_ROUTER` (gpt-oss-120b, reasoning_effort low) for agent/tool routing, `reason()` on `GROQ_MODEL_REASONING` (gpt-oss-120b, reasoning_effort high, JSON mode) for plans/reports, and `chat()` on `GROQ_MODEL_CHAT` (qwen/qwen3.6-27b) for conversation. Replace every `genai`/Gemini call with these and fix the char/4 token-count bug. Add `services/jina_embeddings.py` calling `https://api.jina.ai/v1/embeddings` with `jina-embeddings-v5-text-small` (1024-dim, normalized, task retrieval.passage on write / retrieval.query on read), and migrate the pgvector columns to `vector(1024)` with a re-embed script. Add three FastAPI endpoints — `/api/agent/academic/plan` (takes a subject, builds a Bloom-aligned weekly study plan), `/api/agent/wellness/report` (full non-clinical wellbeing report, escalates to human if needed, never gives crisis methods), `/api/agent/social/plan` — each loading the student's full profile+BKT mastery+trends+memories, calling `reason()`, returning structured JSON, and writing a Jina-embedded memory row. Proxy all three through Express behind auth and `frontend/lib/api.ts`. In the Next.js agent window add a header action button per agent ('Plan your academic activity' which first asks the subject, 'Determine your health', 'Plan your social activity') opening a modal that renders the JSON, keep chat on the CHAT model with top-5 retrieved memories injected, and add a right-side rail per agent (`GET /api/feed/:agent`) showing live education news / campus+LinkedIn / nearby-counselor cards, cached 15 min, keys in Express `.env`. Put all keys/model strings in `.env`, delete Gemini config, and update `AGENTS.md` §5/§8. Confirm live Groq model names at console.groq.com/docs/models before finishing since the catalog changes."

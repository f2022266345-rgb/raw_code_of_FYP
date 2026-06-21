"""
routers/agent_router.py
────────────────────────
Task 5 — FastAPI Routes.

Provides the complete orchestration API for the State-Driven Context Injector.

Routes
──────
POST /api/agent/chat
    Main tutoring endpoint. Express calls this after receiving a student message.
    Runs the full pipeline:
      DB context → State detection → Prompt engineering → Gemini → Response

POST /api/agent/wellness/sync
    Task 3 — Memory Synchronization.
    Called by Express Wellness Agent to write mood/sentiment to agent_memory table.
    Academic Agent retrieves this on its next context fetch.

GET  /api/agent/context/{user_id}/{skill_name}
    Debug / inspection endpoint.
    Returns the full StudentContext snapshot without calling the LLM.

GET  /api/agent/memory/{user_id}
    Returns the latest AgentMemory entry for a user — useful for diagnostics.

Pydantic Models (Task 5)
────────────────────────
  AgentChatRequest   — incoming request from Express
  AgentChatResponse  — outgoing response to Express / frontend
  WellnessSyncRequest — Wellness Agent mood update
  WellnessSyncResponse
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db import get_db, AgentMemoryORM, InitialProfileORM, SessionLocal
from services.context_retriever import get_student_context
from services.state_engine import build_prompt_package, PROMPT_TEMPLATE_A, PROMPT_TEMPLATE_B, PROMPT_TEMPLATE_C
from services.gemini_agent import call_gemini, summarize_conversation_memory, extract_profile_updates, _count_tokens_approx
from services.rag_service import retrieve_rag_context, embed_and_save_exchange, write_cross_agent_memory
from services.agent_registry import detect_off_topic

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["Agent Orchestration"])

ACADEMIC_REFERRAL_TEXT = (
    "It sounds like you're dealing with some pressure right now. I want to make sure you get the right support—"
    "please ask the Wellness Agent about this, as they are equipped to help you feel better."
)

WELLNESS_KEYWORDS = {
    "stress",
    "stressed",
    "anxiety",
    "anxious",
    "panic",
    "depression",
    "depressed",
    "sad",
    "mental",
    "wellness",
    "overwhelmed",
    "burnout",
}

SOCIAL_KEYWORDS = {
    "friends",
    "friend",
    "social",
    "lonely",
    "isolation",
    "peer",
    "group",
    "community",
    "team",
}


def _route_agent(message: str) -> dict:
    """
    Called ONLY when the user is in coordinator/auto mode.
    Explicit agent selections (academic, wellness, social) bypass this entirely
    and are handled directly in Express chatController.js.
    """
    text = (message or "").lower()

    # Wellness signals
    if any(keyword in text for keyword in WELLNESS_KEYWORDS):
        return {"routeTo": "wellness", "reason": "wellness_keywords"}

    # Social signals
    if any(keyword in text for keyword in SOCIAL_KEYWORDS):
        return {"routeTo": "social", "reason": "social_keywords"}

    # Academic signals (explicit check, not just a fallback)
    academic_keywords = {
        "study", "exam", "quiz", "assignment", "homework", "learn",
        "explain", "understand", "concept", "topic", "course", "lecture",
        "programming", "code", "math", "algorithm", "formula", "calculate",
        "help me with", "how does", "what is", "teach me", "practice",
        "problem", "question", "answer", "chapter", "textbook",
    }
    if any(keyword in text for keyword in academic_keywords):
        return {"routeTo": "academic", "reason": "academic_keywords"}

    # Default to coordinator for general / ambiguous messages
    return {"routeTo": "coordinator", "reason": "general_query"}


def _should_redirect_to_wellness(message: str) -> bool:
    text = (message or "").lower()
    return any(keyword in text for keyword in WELLNESS_KEYWORDS)


def _format_chat_for_updates(chat_history: List[dict], database_chat_history: List[dict], message: str, response: str) -> str:
    lines = []
    for item in (database_chat_history or [])[-6:]:
        role = "Assistant" if item.get("role") == "assistant" else "Student"
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(f"[DB] {role}: {content}")
    for item in (chat_history or [])[-6:]:
        role = "Assistant" if item.get("role") == "assistant" else "Student"
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(f"[Session] {role}: {content}")
    if message:
        lines.append(f"[Current] Student: {message}")
    if response:
        lines.append(f"[Current] Assistant: {response}")
    return "\n".join(lines)


def _update_profile_from_chat(
    user_id: str,
    skill_name: str,
    agent_type: str,
    message: str,
    response: str,
    chat_history: List[dict],
    database_chat_history: List[dict],
) -> None:
    """
    Background task after every chat response:
      1. Save exchange to episodic_memory (pgvector RAG)
      2. Write cross-agent memory state
      3. Update InitialProfile with any detected risk signals
      4. Update Digital Twin with a chat-inferred interaction
    """
    db = SessionLocal()
    try:
        # ── 1. Embed exchange into episodic_memory ─────────────────────────
        embed_and_save_exchange(db, user_id, agent_type, message, response)

        # ── 2. Cross-agent memory state write ─────────────────────────────
        conversation_text = _format_chat_for_updates(chat_history, database_chat_history, message, response)
        key_context = f"Topic: {skill_name}. Student asked: {message[:200]}. Agent responded about: {response[:200]}"
        mood_signal = None
        cog_signal = None
        if agent_type == "wellness":
            mood_signal = "stressed" if any(w in message.lower() for w in ("stress", "anxious", "overwhelmed", "sad", "depressed")) else "neutral"
            cog_signal = "critical_struggle" if mood_signal == "stressed" else None
        elif agent_type == "academic":
            cog_signal = "productive_struggle" if any(w in message.lower() for w in ("don't understand", "confused", "help", "stuck")) else "engaged"

        write_cross_agent_memory(db, user_id, agent_type, key_context, mood=mood_signal, cognitive_state=cog_signal)

        # ── 3. Update InitialProfile risk signals ──────────────────────────
        profile = db.query(InitialProfileORM).filter(InitialProfileORM.user_id == user_id).first()
        if profile:
            updates = extract_profile_updates(conversation_text)
            if isinstance(updates, dict):
                score = updates.get("learning_barriers_score")
                wellness_needed = updates.get("wellness_support_needed")
                social_needed = updates.get("social_support_needed")
                if isinstance(score, (int, float)):
                    profile.learning_barriers_score = max(0.0, min(float(score), 1.0))
                if isinstance(wellness_needed, bool):
                    profile.wellness_support_needed = wellness_needed
                if isinstance(social_needed, bool):
                    profile.social_support_needed = social_needed
                db.commit()

        # ── 4. Digital Twin update from chat interaction ───────────────────
        try:
            from services.digital_twin_updater import DigitalTwinUpdater
            updater = DigitalTwinUpdater(db)
            # Chat messages are interactions with type "chat" — approximate skill_id=0
            chat_interaction = {
                "skill_id": 0,
                "problem_id": 0,
                "correct": True,  # chat = positive engagement by default
                "time_on_task_ms": 8000,
                "hints_used": 0,
                "attempt_count": 1,
                "mood": mood_signal,
                "confidence_before": 0.5,
                "confidence_after": 0.6,
                "interaction_type": f"chat_{agent_type}",
            }
            updater.process_new_interaction(user_id, chat_interaction)
        except Exception as twin_exc:
            logger.debug("Digital Twin chat update skipped: %s", twin_exc)

    except Exception as exc:
        logger.warning("Profile update failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models (Task 5 — Output Requirements)
# ─────────────────────────────────────────────────────────────────────────────

class AgentChatRequest(BaseModel):
    """
    Incoming request from Express when a student sends a message.

    Required:
        user_id:    The UUID from the users table (passed via Express JWT decode).
        skill_name: The skill currently being studied (from active BKT session).
        message:    The student's raw message.

    Optional:
        agent_type:     Which sub-agent is handling this (academic | wellness | coordinator).
        student_name:   Pulled from InitialProfile.user_profile.name by Express.
    """
    user_id: str = Field(..., description="User UUID from the users table")
    skill_name: str = Field(..., description="The BKT skill currently being studied")
    message: str = Field(..., min_length=1, max_length=2000, description="Student's message")
    agent_type: str = Field(default="academic", description="academic | wellness | social | coordinator")
    student_name: str = Field(default="the student", description="Student's display name")
    chat_history: List[dict] = Field(default_factory=list, description="Recent in-session chat history from frontend")
    database_chat_history: List[dict] = Field(default_factory=list, description="Recent persisted chat history from database")
    orchestration_context: dict = Field(default_factory=dict, description="Coordinator rules + hidden/profile context")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "a3f8-...",
                "skill_name": "Pythagorean Theorem",
                "message": "I don't understand when to use the formula",
                "agent_type": "academic",
                "student_name": "Ali",
                "chat_history": [
                    {"role": "user", "content": "Can we revise the formula?"},
                    {"role": "assistant", "content": "Sure. What part is confusing?"},
                ],
            }
        }


class AgentChatResponse(BaseModel):
    """
    Outgoing LLM response returned to Express (and then to the frontend).

    Contains the response text plus debugging metadata about the state decision.
    """
    agent_type: str
    response: str
    routed_agent: str
    coordinator_decision: Optional[dict] = None
    # State engine metadata
    state: str                           # INTELLIGENT | STRUGGLING | DEVELOPING
    persona: str                         # Peer-to-Peer | Socratic Tutor | Coach
    p_mastery: float                     # [0, 1]
    bloom_level: int                     # [1-6]
    needs_pgvector: bool
    # Prompt metadata
    system_instruction_tokens: int       # Approximate token count
    system_instruction_preview: str      # First 100 chars for debugging


class WellnessSyncRequest(BaseModel):
    """
    Task 3 — Wellness Agent syncs emotional state to AgentMemory.

    Called by Express Wellness Agent when it detects mood/sentiment changes
    (e.g., after a wellness chat session or crisis detection).
    The Academic Agent will read this on its next context retrieval.
    """
    user_id: str = Field(..., description="User UUID")
    mood: Optional[str] = Field(None, description="Detected mood: Stressed | Anxious | Focused | Overwhelmed...")
    sentiment_label: Optional[str] = Field(None, description="positive | neutral | negative")
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0, description="Sentiment score [-1, 1]")
    cognitive_state: Optional[str] = Field(None, description="FLOW_STATE | CRITICAL_STRUGGLE | DISENGAGED | PRODUCTIVE_STRUGGLE | NEUTRAL")
    payload: Optional[dict] = Field(None, description="Any extra agent-specific data")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "a3f8-...",
                "mood": "Anxious",
                "sentiment_label": "negative",
                "sentiment_score": -0.6,
                "cognitive_state": "CRITICAL_STRUGGLE",
            }
        }


class WellnessSyncResponse(BaseModel):
    success: bool
    message: str
    memory_id: int


class MemorySummaryRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=80)
    conversation_text: str = Field(..., min_length=1, max_length=12000)


class MemorySummaryResponse(BaseModel):
    topic: str
    summary: str


class OnboardingSynthesizeRequest(BaseModel):
    user_id: str
    raw_profile_text: str


class StudentContextResponse(BaseModel):
    """Debug endpoint — returns raw StudentContext without calling LLM."""
    user_id: str
    skill_name: str
    p_mastery: float
    bloom_level: int
    language_barrier_risk: float
    sentiment_label: str
    mood: str
    effective_mood: str
    effective_sentiment: str
    cognitive_state: Optional[str]
    wellness_mood: Optional[str]
    needs_urdu_support: bool
    study_pace: str
    dominant_style: str
    practice_count: int


class PromptTemplatesResponse(BaseModel):
    """Task 5 — Returns the prompt template strings for both conditions."""
    condition_a_label: str
    condition_a_trigger: str
    condition_a_template: str
    condition_b_label: str
    condition_b_trigger: str
    condition_b_template: str
    condition_c_label: str
    condition_c_template: str


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _dominant_style(styles: dict) -> str:
    if not styles:
        return "mixed"
    return max(styles, key=lambda k: styles.get(k, 0), default="mixed")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=AgentChatResponse, summary="State-Driven Agent Chat")
async def agent_chat(
    payload: AgentChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    **Main Orchestration Endpoint** (Task 5).

    Full pipeline:
      1. Retrieve StudentContext from DB (Task 1)
      2. Determine state + build prompt package (Task 2)
      3. Optionally fetch pgvector scaffolding (Task 4)
      4. Call Gemini with token-optimized prompt (Task 4)
      5. Return structured response

    Called by Express `/api/chat` controller as a proxy.
    """
    logger.info(
        "AgentChat | user=%s skill=%s agent=%s",
        payload.user_id, payload.skill_name, payload.agent_type,
    )

    # ── Task 1: Context Retrieval (9 DB queries) ──────────────────────────
    routed_agent = payload.agent_type
    routing_decision = None
    if payload.agent_type in {"coordinator", "router", "auto"}:
        routing_decision = _route_agent(payload.message)
        routed_agent = routing_decision.get("routeTo", "academic")

    ctx = get_student_context(
        db=db,
        user_id=payload.user_id,
        skill_name=payload.skill_name,
        user_message=payload.message,
        agent_type=routed_agent,
    )

    # ── RAG: Retrieve relevant context from pgvector ──────────────────────
    rag_context = retrieve_rag_context(
        db=db,
        user_id=payload.user_id,
        query_text=payload.message,
        agent_type=routed_agent,
        top_k_episodic=3,
        top_k_knowledge=2,
    )

    # ── Task 2: State + Prompt Engineering (full context, no truncation) ──
    prompt_pkg = build_prompt_package(
        ctx=ctx,
        user_message=payload.message,
        student_name=payload.student_name,
        agent_type=routed_agent,
        orchestration_context=payload.orchestration_context,
        rag_context=rag_context,
    )

    # ── Hard off-topic guard (runs BEFORE LLM call, saves API cost) ─────────
    off_topic_redirect = detect_off_topic(routed_agent, payload.message)
    if off_topic_redirect:
        response_text = off_topic_redirect
    elif routed_agent == "academic" and _should_redirect_to_wellness(payload.message):
        response_text = ACADEMIC_REFERRAL_TEXT
    else:
        # RAG context is already embedded in the system prompt via build_prompt_package,
        # so we skip the internal pgvector call inside call_gemini (needs_pgvector=False)
        # to avoid burning an extra embedding API call per request.
        response_text = call_gemini(
            system_instruction=prompt_pkg.system_instruction,
            user_message=prompt_pkg.user_message,
            needs_pgvector=False,
            skill_name=payload.skill_name,
            db=db,
            chat_history=payload.chat_history,
            database_chat_history=payload.database_chat_history,
            user_id=payload.user_id,
        )

    token_count = _count_tokens_approx(prompt_pkg.system_instruction)

    background_tasks.add_task(
        _update_profile_from_chat,
        payload.user_id,
        payload.skill_name,
        routed_agent,
        payload.message,
        response_text,
        payload.chat_history,
        payload.database_chat_history,
    )

    return AgentChatResponse(
        agent_type=routed_agent,
        response=response_text,
        routed_agent=routed_agent,
        coordinator_decision=routing_decision or payload.orchestration_context.get("coordinatorDecision"),
        state=prompt_pkg.state,
        persona=prompt_pkg.persona,
        p_mastery=ctx.p_mastery,
        bloom_level=ctx.bloom_level,
        needs_pgvector=prompt_pkg.needs_pgvector,
        system_instruction_tokens=token_count,
        system_instruction_preview=prompt_pkg.system_instruction[:100],
    )



@router.post(
    "/router",
    summary="Lightweight Router Model — returns routing decision JSON",
)
async def router_classify(payload: dict):
    """
    Lightweight routing endpoint used by Express to decide which agent should
    handle an incoming message. Returns a JSON like {"routeTo": "wellness", "reason": "wellness_keywords"}.
    """
    message = str(payload.get("message") or "")
    decision = _route_agent(message)
    return {"decision": decision}


@router.post(
    "/wellness/sync",
    response_model=WellnessSyncResponse,
    summary="Wellness Agent → Memory Sync (Task 3)",
)
async def wellness_sync(payload: WellnessSyncRequest, db: Session = Depends(get_db)):
    """
    **Task 3 — Memory Synchronization.**

    Called by Express Wellness Agent (or directly by the frontend Wellness chat)
    to persist the latest mood and emotional state to the `agent_memory` table.

    The Academic Agent reads this table on every context retrieval, so any
    update here is immediately reflected in the next academic interaction.
    This implements real-time cross-agent emotional state propagation.
    """
    logger.info(
        "WellnessSync | user=%s mood=%s sentiment=%s cognitive=%s",
        payload.user_id, payload.mood, payload.sentiment_label, payload.cognitive_state,
    )

    memory = AgentMemoryORM(
        user_id=payload.user_id,
        source_agent="wellness",
        mood=payload.mood,
        sentiment_label=payload.sentiment_label,
        sentiment_score=payload.sentiment_score,
        cognitive_state=payload.cognitive_state,
        payload=payload.payload,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)

    logger.info("AgentMemory row created: id=%d for user=%s", memory.id, payload.user_id)

    return WellnessSyncResponse(
        success=True,
        message=f"Memory synced. Academic Agent will apply mood='{payload.mood}' on next interaction.",
        memory_id=memory.id,
    )


@router.get(
    "/context/{user_id}/{skill_name}",
    response_model=StudentContextResponse,
    summary="Debug: Get Student Context Snapshot",
)
async def get_context_snapshot(
    user_id: str,
    skill_name: str,
    db: Session = Depends(get_db),
):
    """
    **Debug endpoint** — returns the full StudentContext snapshot for inspection.
    Runs all 4 DB queries (Task 1) without calling the LLM.

    Use this to verify context retrieval is working correctly before testing
    the full `/api/agent/chat` pipeline.
    """
    ctx = get_student_context(db=db, user_id=user_id, skill_name=skill_name)

    return StudentContextResponse(
        user_id=ctx.user_id,
        skill_name=ctx.skill_name,
        p_mastery=round(ctx.p_mastery, 4),
        bloom_level=ctx.bloom_level,
        language_barrier_risk=round(ctx.language_barrier_risk, 3),
        sentiment_label=ctx.sentiment_label,
        mood=ctx.mood,
        effective_mood=ctx.effective_mood,
        effective_sentiment=ctx.effective_sentiment,
        cognitive_state=ctx.cognitive_state,
        wellness_mood=ctx.wellness_mood,
        needs_urdu_support=ctx.needs_urdu_support,
        study_pace=ctx.study_pace,
        dominant_style=_dominant_style(ctx.learning_styles),
        practice_count=ctx.practice_count,
    )


@router.get(
    "/memory/{user_id}",
    summary="Debug: Get Latest Agent Memory Entry",
)
async def get_agent_memory(user_id: str, db: Session = Depends(get_db)):
    """Returns the most recent AgentMemory entry for a user."""
    entry = (
        db.query(AgentMemoryORM)
        .filter(AgentMemoryORM.user_id == user_id)
        .order_by(desc(AgentMemoryORM.created_at))
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="No agent memory found for this user.")

    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "source_agent": entry.source_agent,
        "mood": entry.mood,
        "sentiment_label": entry.sentiment_label,
        "sentiment_score": entry.sentiment_score,
        "cognitive_state": entry.cognitive_state,
        "payload": entry.payload,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@router.get(
    "/prompt-templates",
    response_model=PromptTemplatesResponse,
    summary="Task 5: Get Prompt Template Strings",
)
async def get_prompt_templates():
    """
    **Task 5 — Returns the prompt template strings** for Condition A and B.

    Use this to review, validate, or adjust the prompt engineering logic.
    """
    return PromptTemplatesResponse(
        condition_a_label="Peer-to-Peer (Intelligent / Mastery)",
        condition_a_trigger="p_mastery > 0.7 OR bloom_level >= 4",
        condition_a_template=PROMPT_TEMPLATE_A,
        condition_b_label="Socratic Tutor (Struggling / Scaffolding)",
        condition_b_trigger="p_mastery < 0.4 OR language_barrier_risk > 0.6",
        condition_b_template=PROMPT_TEMPLATE_B,
        condition_c_label="Encouraging Coach (Developing / Default)",
        condition_c_template=PROMPT_TEMPLATE_C,
    )


@router.post(
    "/memory/summary",
    response_model=MemorySummaryResponse,
    summary="Generate AI memory summary for a topic",
)
async def memory_summary(payload: MemorySummaryRequest):
    summary = summarize_conversation_memory(
        topic=payload.topic,
        conversation_text=payload.conversation_text,
    )

    return MemorySummaryResponse(topic=payload.topic, summary=summary)


@router.post("/onboarding/synthesize", summary="Synthesize onboarding profile into pgvector")
async def onboarding_synthesize(
    payload: OnboardingSynthesizeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    from services.gemini_agent import synthesize_and_embed_student_profile
    background_tasks.add_task(
        synthesize_and_embed_student_profile,
        db,
        payload.user_id,
        payload.raw_profile_text
    )
    return {"status": "synthesis_started"}


class StreamRequest(BaseModel):
    user_id: str
    thread_id: str
    message: str
    skill_name: Optional[str] = None
    agent_type: Optional[str] = None
    student_name: Optional[str] = None
    chat_history: Optional[list] = None
    database_chat_history: Optional[list] = None
    orchestration_context: Optional[dict] = None
    stream: Optional[bool] = None

    class Config:
        extra = "ignore"


@router.post("/stream", summary="Stream LangGraph response via SSE")
async def stream_agent(payload: StreamRequest):
    import json
    from fastapi.responses import StreamingResponse
    from langchain_core.messages import HumanMessage
    import os
    from app.graph.workflow import builder
    from langgraph.store.memory import InMemoryStore

    async def event_generator():
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            raw_db_url = os.getenv("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/FYP_backup")
            db_url = raw_db_url.replace("+psycopg", "")
            # Using native AsyncPostgresSaver as requested in Part 1
            async with AsyncPostgresSaver.from_conn_string(db_url) as checkpointer:
                await checkpointer.setup()
                
                store = InMemoryStore()
                graph = builder.compile(checkpointer=checkpointer, store=store)
                
                config = {
                    "configurable": {
                        "thread_id": payload.thread_id,
                        "user_id": payload.user_id
                    }
                }
                
                state = {
                    "messages": [HumanMessage(content=payload.message)],
                    "user_id": payload.user_id,
                    "thread_id": payload.thread_id,
                    "active_agent": "academic",
                    "risk_level": "Standard",
                    "student_context": {}
                }
                # Using astream_events to yield tokens as they arrive
                async for event in graph.astream_events(state, config, version="v2"):
                    kind = event["event"]
                    if kind == "on_chat_model_stream":
                        chunk = event["data"]["chunk"]
                        if hasattr(chunk, "content") and chunk.content:
                            yield f"data: {json.dumps({'token': chunk.content})}\n\n"
                
                # Retrieve final state and attach UI Tool Window Sync metadata
                final_state = await graph.aget_state(config)
                agent = final_state.values.get("active_agent", "academic")
                
                # Mock extracting youtube_links for now, typically this would be parsed from state
                # or from a specific ToolMessage inside final_state.values["messages"]
                metadata = {
                    "active_agent": agent,
                    "youtube_links": ["https://youtube.com/watch?v=dQw4w9WgXcQ"] if agent == "academic" else []
                }
                yield f"data: {json.dumps({'metadata': metadata})}\n\n"
                yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class AnalyzeMetricsRequest(BaseModel):
    user_id: str

@router.post("/metrics/analyze", summary="Triggered by Express Cron to analyze 2-week progress")
async def analyze_metrics(payload: AnalyzeMetricsRequest, db: Session = Depends(get_db)):
    """
    Called by the Express node-cron scheduler every 2 weeks per user.
    Tries to run the Semester LangGraph Workflow. Falls back to a direct
    DB-query + LLM analysis if LangGraph dependencies are not available.
    """
    try:
        from app.graph.semester_graph import semester_graph
        state_input = {
            "user_id": payload.user_id,
            "data": {},
            "analysis": "",
            "is_critical": False
        }
        final_state = await semester_graph.ainvoke(state_input)
        return {
            "status": "Critical" if final_state.get("is_critical") else "OK",
            "message": f"Semester graph completed for user {payload.user_id}",
            "analysis": final_state.get("analysis", ""),
            "progress_data": final_state.get("data", {}),
        }
    except ImportError:
        logger.warning("LangGraph not available — running direct metrics analysis fallback.")
    except Exception as exc:
        logger.warning("Semester graph failed (%s) — falling back to direct analysis.", exc)

    # ── Direct fallback: query DB + call LLM directly ─────────────────────────
    try:
        import json
        from datetime import datetime, timedelta, timezone
        from db import BktSkillMasteryORM, InteractionLogORM, ProgressSnapshotORM
        from services.gemini_agent import _get_openai_client, _iter_model_candidates

        now = datetime.now(timezone.utc)
        two_weeks_ago = now - timedelta(days=14)

        logs = db.query(InteractionLogORM).filter(
            InteractionLogORM.user_id == payload.user_id,
            InteractionLogORM.created_at >= two_weeks_ago
        ).all()

        bkt = db.query(BktSkillMasteryORM).filter(
            BktSkillMasteryORM.user_id == payload.user_id
        ).all()

        grades = {s.skill_name: s.p_mastery for s in bkt}
        attendance = min(len(logs) / 14.0, 1.0) if logs else 0.0
        progress_data = {
            "grades": grades,
            "attendance_rate": attendance,
            "total_interactions_last_14_days": len(logs),
        }

        # Snapshot
        snapshot = ProgressSnapshotORM(
            user_id=payload.user_id,
            grades=grades,
            attendance_rate=attendance,
            engagement_metrics={"total_interactions": len(logs)},
        )
        db.add(snapshot)
        db.commit()

        # LLM analysis
        client = _get_openai_client()
        is_critical = False
        analysis = "Automated analysis unavailable."

        if client:
            prompt = (
                f"You are an automated academic evaluator. Analyze this 14-day student progress:\n"
                f"{json.dumps(progress_data, indent=2)}\n\n"
                "If the student has very low mastery (p_mastery < 0.2 across most skills) or near-zero "
                "attendance, set is_critical=true. Otherwise is_critical=false.\n"
                "Respond ONLY with valid JSON: {\"analysis\": \"...\", \"is_critical\": true/false}"
            )
            try:
                resp = client.chat.completions.create(
                    model=_iter_model_candidates()[0],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=300,
                )
                result = json.loads(resp.choices[0].message.content)
                is_critical = result.get("is_critical", False)
                analysis = result.get("analysis", "")
            except Exception as llm_exc:
                logger.warning("LLM analysis failed: %s", llm_exc)
                # Simple rule-based fallback
                avg_mastery = sum(grades.values()) / len(grades) if grades else 0
                is_critical = avg_mastery < 0.2 or attendance < 0.1
                analysis = f"Rule-based: avg_mastery={avg_mastery:.2f}, attendance={attendance:.2f}"

        return {
            "status": "Critical" if is_critical else "OK",
            "message": f"Direct analysis completed for user {payload.user_id}",
            "analysis": analysis,
            "progress_data": progress_data,
        }
    except Exception as fallback_exc:
        logger.error("Metrics analysis fallback also failed: %s", fallback_exc)
        return {
            "status": "OK",
            "message": "Analysis could not be completed",
            "analysis": str(fallback_exc),
            "progress_data": {},
        }


# ─── Human Counselor: Apply parameter updates ─────────────────────────────────

class CounselorUpdateRequest(BaseModel):
    user_id: str
    case_id: Optional[str] = None
    counselor_notes: Optional[str] = ""
    updates: dict = Field(default_factory=dict)
    # updates can contain: pacing, chunking, languageSupport, wellness_support_needed,
    # social_support_needed, learning_barriers_score, bloom_level, etc.

@router.post("/counselor/apply-updates", summary="Apply human counselor parameter updates to student profile")
async def counselor_apply_updates(payload: CounselorUpdateRequest, db: Session = Depends(get_db)):
    """
    Called by Express when a human counselor reviews and submits parameter updates
    for a student's case. Updates the InitialProfileORM so the next tutoring
    session reflects the counselor's intervention.
    """
    try:
        profile = db.query(InitialProfileORM).filter(
            InitialProfileORM.user_id == payload.user_id
        ).first()

        if not profile:
            raise HTTPException(status_code=404, detail=f"No profile found for user {payload.user_id}")

        applied = {}
        updates = payload.updates

        # Bloom level adjustment
        if "bloom_level" in updates and isinstance(updates["bloom_level"], int):
            profile.bloom_level = max(1, min(6, updates["bloom_level"]))
            applied["bloom_level"] = profile.bloom_level

        # Learning barriers
        if "learning_barriers_score" in updates:
            val = float(updates["learning_barriers_score"])
            profile.learning_barriers_score = max(0.0, min(1.0, val))
            applied["learning_barriers_score"] = profile.learning_barriers_score

        # Wellness / social flags
        if "wellness_support_needed" in updates and isinstance(updates["wellness_support_needed"], bool):
            profile.wellness_support_needed = updates["wellness_support_needed"]
            applied["wellness_support_needed"] = profile.wellness_support_needed

        if "social_support_needed" in updates and isinstance(updates["social_support_needed"], bool):
            profile.social_support_needed = updates["social_support_needed"]
            applied["social_support_needed"] = profile.social_support_needed

        # Cognitive rules (pacing, chunking, languageSupport)
        cognitive_keys = ["pacing", "chunking", "languageSupport"]
        cognitive_updates = {k: updates[k] for k in cognitive_keys if k in updates}
        if cognitive_updates:
            existing_rules = profile.cognitive_rules or {}
            existing_rules.update(cognitive_updates)
            if payload.counselor_notes:
                existing_rules["counselor_notes"] = payload.counselor_notes[:512]
            if payload.case_id:
                existing_rules["last_case_id"] = payload.case_id
            profile.cognitive_rules = existing_rules
            applied["cognitive_rules"] = cognitive_updates

        db.commit()
        logger.info(
            "Counselor updates applied for user %s (case=%s): %s",
            payload.user_id, payload.case_id, applied
        )

        return {
            "success": True,
            "user_id": payload.user_id,
            "case_id": payload.case_id,
            "applied": applied,
            "message": "Student profile updated with counselor parameters. Changes take effect on next chat."
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("counselor_apply_updates failed: %s", exc)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))

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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db import get_db, AgentMemoryORM
from services.context_retriever import get_student_context
from services.state_engine import build_prompt_package, PROMPT_TEMPLATE_A, PROMPT_TEMPLATE_B, PROMPT_TEMPLATE_C
from services.gemini_agent import call_gemini

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["Agent Orchestration"])


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

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "a3f8-...",
                "skill_name": "Pythagorean Theorem",
                "message": "I don't understand when to use the formula",
                "agent_type": "academic",
                "student_name": "Ali",
            }
        }


class AgentChatResponse(BaseModel):
    """
    Outgoing LLM response returned to Express (and then to the frontend).

    Contains the response text plus debugging metadata about the state decision.
    """
    agent_type: str
    response: str
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
async def agent_chat(payload: AgentChatRequest, db: Session = Depends(get_db)):
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

    # ── Task 1: Context Retrieval ─────────────────────────────────────────
    ctx = get_student_context(
        db=db,
        user_id=payload.user_id,
        skill_name=payload.skill_name,
    )

    # ── Task 2: State + Prompt Engineering ───────────────────────────────
    prompt_pkg = build_prompt_package(
        ctx=ctx,
        user_message=payload.message,
        student_name=payload.student_name,
        agent_type=payload.agent_type,
    )

    # ── Task 4: Token-Optimized Gemini Call ──────────────────────────────
    response_text = call_gemini(
        system_instruction=prompt_pkg.system_instruction,
        user_message=prompt_pkg.user_message,
        needs_pgvector=prompt_pkg.needs_pgvector,
        skill_name=payload.skill_name,
        db=db,
    )

    # Approximate token count for response metadata
    from services.gemini_agent import _count_tokens_approx, _truncate_to_token_limit
    token_count = _count_tokens_approx(prompt_pkg.system_instruction)

    return AgentChatResponse(
        agent_type=payload.agent_type,
        response=response_text,
        state=prompt_pkg.state,
        persona=prompt_pkg.persona,
        p_mastery=ctx.p_mastery,
        bloom_level=ctx.bloom_level,
        needs_pgvector=prompt_pkg.needs_pgvector,
        system_instruction_tokens=token_count,
        system_instruction_preview=prompt_pkg.system_instruction[:100],
    )


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

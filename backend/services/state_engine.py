"""
services/state_engine.py
─────────────────────────
Task 2 — State-Driven Prompt Engineering.

Evaluates the StudentContext from context_retriever.py and:
  1. Determines the student's STATE (INTELLIGENT | STRUGGLING | DEVELOPING)
  2. Selects the correct persona and token-optimized system prompt
  3. Returns a PromptPackage ready to send to the Gemini API

Condition A (INTELLIGENT / Mastery):
  Trigger  : p_mastery > 0.7  OR  bloom_level >= 4
  Persona  : Peer-to-Peer
    Constraint: Direct, practical answers first. Expand with examples when useful.

Condition B (STRUGGLING / Scaffolding):
  Trigger  : p_mastery < 0.4  OR  language_barrier_risk > 0.6
  Persona  : Socratic Tutor
    Constraint: Start with a guiding question and then scaffold clearly.
                            Calibrate to learning_preferences and avoid abrupt short replies.

Condition C (DEVELOPING) — default between A and B.
  Persona  : Encouraging Coach
    Constraint: Clear explanation + one practice hint, with enough detail to complete the thought.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from services.context_retriever import StudentContext
from services.agent_registry import get_agent_profile

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# State labels
# ─────────────────────────────────────────────────────────────────────────────

StudentState = Literal["INTELLIGENT", "STRUGGLING", "DEVELOPING"]

# ─────────────────────────────────────────────────────────────────────────────
# Prompt Templates (Task 5 — Output Requirements)
# ─────────────────────────────────────────────────────────────────────────────

# ── Condition A: Peer-to-Peer (Mastery / Intelligent) ─────────────────────────
PROMPT_TEMPLATE_A = """You are a peer tutor helping {name} with {skill_name}.
Persona: Peer-to-Peer. Mood detected: {mood}. Cognitive state: {cognitive_state}.
Rules: Be clear and conversational. Prefer practical examples over rigid theory.
Give a complete answer by default, not a cut-off or one-line response.
Bloom level {bloom_level}/6 — use advanced vocabulary appropriate to this level."""

# ── Condition B: Socratic Tutor (Struggling / Scaffolding) ────────────────────
PROMPT_TEMPLATE_B = """You are a Socratic tutor helping {name} with {skill_name}.
Persona: Guiding Mentor. Student mood: {mood}. Language barrier risk: {lang_risk_pct}%.
Rules: Start with a guiding question, then give a small hint if needed.
Then provide a complete scaffolded explanation without being overly brief.
Calibrate to their learning style ({dominant_style}). Keep tone supportive and natural.{urdu_note}"""

# ── Condition C: Encouraging Coach (Developing) ────────────────────────────────
PROMPT_TEMPLATE_C = """You are an encouraging tutor helping {name} with {skill_name}.
Persona: Supportive Coach. Student mood: {mood}. Study pace: {study_pace}.
Rules: Provide a clear explanation followed by one practice hint.
Make the response complete and coherent unless the student asks for a very short reply.
Keep tone warm, human, and practical. Avoid overly strict formatting.{urdu_note}"""

# ─────────────────────────────────────────────────────────────────────────────
# PromptPackage — output of the state engine
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PromptPackage:
    """
    The fully rendered prompt ready for the Gemini API.

    Only system_instruction + user_message are sent to the LLM (Task 4).
    The state and ctx fields are for logging/debugging only.
    """
    state: StudentState
    persona: str
    system_instruction: str    # ≤ 150 tokens — the only system content sent
    user_message: str          # The student's actual question
    needs_pgvector: bool       # True when p_mastery < 0.4 (Task 4)
    ctx_snapshot: dict         # Serialized context for logging


# ─────────────────────────────────────────────────────────────────────────────
# State Determination
# ─────────────────────────────────────────────────────────────────────────────

def determine_state(ctx: StudentContext) -> StudentState:
    """
    Applies priority-ordered condition checks to classify the student's state.

    Priority order (highest to lowest):
      1. STRUGGLING  — most urgent, triggers scaffolding mode
      2. INTELLIGENT — mastery confirmed, peer-mode appropriate
      3. DEVELOPING  — default
    """
    # ── Condition B: Struggling takes highest priority ─────────────────────
    if ctx.p_mastery < 0.4 or ctx.language_barrier_risk > 0.6:
        logger.debug(
            "State=STRUGGLING (p_mastery=%.3f, lang_risk=%.2f)",
            ctx.p_mastery, ctx.language_barrier_risk,
        )
        return "STRUGGLING"

    # ── Condition A: Mastery / Intelligent ─────────────────────────────────
    if ctx.p_mastery > 0.7 or ctx.bloom_level >= 4:
        logger.debug(
            "State=INTELLIGENT (p_mastery=%.3f, bloom=%d)",
            ctx.p_mastery, ctx.bloom_level,
        )
        return "INTELLIGENT"

    # ── Condition C: Developing (default) ──────────────────────────────────
    logger.debug("State=DEVELOPING (p_mastery=%.3f, bloom=%d)", ctx.p_mastery, ctx.bloom_level)
    return "DEVELOPING"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dominant_learning_style(styles: dict) -> str:
    """Returns the label of the highest-scoring VARK dimension."""
    vark = {
        "visual": styles.get("visual", 0),
        "auditory": styles.get("auditory", 0),
        "reading": styles.get("reading", 0),
        "kinesthetic": styles.get("kinesthetic", 0),
    }
    if not any(vark.values()):
        return "mixed"
    return max(vark, key=vark.get)


def _urdu_note(ctx: StudentContext) -> str:
    if ctx.needs_urdu_support:
        return (
            " When introducing new terms, optionally add the Urdu equivalent "
            "in parentheses (e.g., 'loop (لوپ)'). Keep language simple and clear."
        )
    return ""


def _student_name(ctx: StudentContext) -> str:
    """Best-effort name — falls back to 'the student'."""
    return "the student"  # caller can override with profile data


def _agent_directive(agent_type: str) -> str:
    profile = get_agent_profile(agent_type)
    return profile.guardrails


# ─────────────────────────────────────────────────────────────────────────────
# Main: Build Prompt Package
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt_package(
    ctx: StudentContext,
    user_message: str,
    student_name: str = "the student",
    agent_type: str = "coordinator",
    orchestration_context: dict | None = None,
) -> PromptPackage:
    """
    Determines the student's state and renders the appropriate system prompt.

    Args:
        ctx:           Full StudentContext from context_retriever.
        user_message:  The raw message the student just typed.
        student_name:  Pulled from InitialProfile.user_profile.name.

    Returns:
        A PromptPackage with the rendered system_instruction (≤ 150 tokens)
        and the user_message. Includes needs_pgvector flag.
    """
    state = determine_state(ctx)
    mood = ctx.effective_mood
    cognitive_state = ctx.cognitive_state or "NEUTRAL"
    dominant_style = _dominant_learning_style(ctx.learning_styles)
    urdu_note = _urdu_note(ctx)

    orchestration_context = orchestration_context or {}

    if state == "INTELLIGENT":
        persona = "Peer-to-Peer"
        system_instruction = PROMPT_TEMPLATE_A.format(
            name=student_name,
            skill_name=ctx.skill_name,
            mood=mood,
            cognitive_state=cognitive_state,
            bloom_level=ctx.bloom_level,
        )

    elif state == "STRUGGLING":
        persona = "Socratic Tutor"
        system_instruction = PROMPT_TEMPLATE_B.format(
            name=student_name,
            skill_name=ctx.skill_name,
            mood=mood,
            lang_risk_pct=int(ctx.language_barrier_risk * 100),
            dominant_style=dominant_style,
            urdu_note=urdu_note,
        )

    else:  # DEVELOPING
        persona = "Encouraging Coach"
        system_instruction = PROMPT_TEMPLATE_C.format(
            name=student_name,
            skill_name=ctx.skill_name,
            mood=mood,
            study_pace=ctx.study_pace,
            urdu_note=urdu_note,
        )

    # pgvector needed when student is struggling AND hasn't practiced much
    needs_pgvector = ctx.p_mastery < 0.4 and ctx.practice_count < 3

    profile_ctx = orchestration_context.get("profile") or {}
    hidden_ctx = orchestration_context.get("hiddenState") or {}
    coordinator_decision = orchestration_context.get("coordinatorDecision") or {}

    cultural_context = profile_ctx.get("culturalContext") or {}
    learning_prefs = profile_ctx.get("learningPreferences") or {}
    cognitive_rules = profile_ctx.get("cognitiveRules") or {}

    orchestration_note = (
        "\nOrchestration Context: "
        f"Bloom={orchestration_context.get('bloomLevel', ctx.bloom_level)}/6; "
        f"LanguagePreference={orchestration_context.get('languagePreference', ctx.language_preference)}; "
        f"CulturalRegion={cultural_context.get('region', 'Pakistan-context')}; "
        f"CognitiveChunking={cognitive_rules.get('chunking', 'medium-chunks')}; "
        f"Frustration={hidden_ctx.get('frustrationEstimate', 'n/a')}; "
        f"Readiness={hidden_ctx.get('readinessEstimate', 'n/a')}; "
        f"Engagement={hidden_ctx.get('engagementEstimate', 'n/a')}."
        " Use culturally aware examples, align complexity to Bloom level, and if language risk is high provide bilingual support."
        " Keep cognitive load manageable by chunking explanation into short progressive steps."
    )

    if coordinator_decision:
        orchestration_note += (
            f" Coordinator routing rationale: {coordinator_decision.get('matchedRule', 'n/a')}"
            f" ({coordinator_decision.get('rationale', 'n/a')})."
        )

    system_instruction = (
        f"{system_instruction}\n{_agent_directive(agent_type)}{orchestration_note}"
    )

    ctx_snapshot = {
        "user_id": ctx.user_id,
        "skill_name": ctx.skill_name,
        "p_mastery": round(ctx.p_mastery, 3),
        "bloom_level": ctx.bloom_level,
        "language_barrier_risk": round(ctx.language_barrier_risk, 2),
        "sentiment_label": ctx.effective_sentiment,
        "mood": mood,
        "cognitive_state": cognitive_state,
        "state": state,
        "needs_pgvector": needs_pgvector,
        "orchestration_context": orchestration_context,
    }

    logger.info(
        "PromptPackage | state=%s persona=%s p_mastery=%.3f bloom=%d needs_pgvector=%s",
        state, persona, ctx.p_mastery, ctx.bloom_level, needs_pgvector,
    )

    return PromptPackage(
        state=state,
        persona=persona,
        system_instruction=system_instruction,
        user_message=user_message,
        needs_pgvector=needs_pgvector,
        ctx_snapshot=ctx_snapshot,
    )

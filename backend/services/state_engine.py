"""
services/state_engine.py
─────────────────────────
State-Driven Prompt Engineering for LUMINA agents.

Evaluates StudentContext and builds a rich, complete system prompt that tells
the LLM:
  • Who the student is (profile, university, major, cognitive rules)
  • What their live Digital Twin state says (frustration, motivation, at-risk)
  • What agent they are talking to and what scope that agent has
  • What RAG context is relevant to this query
  • What off-topic handling to apply

Agent states:
  INTELLIGENT  — p_mastery > 0.70  OR  bloom_level >= 4
  STRUGGLING   — p_mastery < 0.40  OR  language_barrier_risk > 0.60
  DEVELOPING   — default

Every prompt is complete (no 150-token limit truncation at this layer).
The token limit is raised to 3000 in call_gemini so the full context reaches Gemini.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from services.context_retriever import StudentContext

logger = logging.getLogger(__name__)

StudentState = Literal["INTELLIGENT", "STRUGGLING", "DEVELOPING"]

BLOOM_LABELS = {
    1: "Remember",
    2: "Understand",
    3: "Apply",
    4: "Analyse",
    5: "Evaluate",
    6: "Create",
}

# ─────────────────────────────────────────────────────────────────────────────
# Agent scope definitions (enforcement + identity)
# ─────────────────────────────────────────────────────────────────────────────

_AGENT_SCOPE = {
    "academic": {
        "identity": "Academic Support Agent",
        "scope_desc": (
            "You help students with academic topics: study strategies, concept explanations, "
            "problem-solving, skill gaps, exam preparation, assignments, Bloom-level learning, "
            "and course planning. You cover all academic subjects including math, science, and programming."
        ),
        "off_topic_rule": (
            "When the student seems emotionally distressed, gently acknowledge it and redirect them: "
            "say 'I can hear you are going through a tough time. Please talk to the Wellness Agent "
            "who is better equipped to support you emotionally. I am here for academics whenever you are ready.'"
        ),
        "persona_rule": "Be a knowledgeable peer tutor: clear, practical, and adapt to the student's Bloom level.",
    },
    "wellness": {
        "identity": "Wellness Agent",
        "scope_desc": (
            "You support the student's mental and emotional wellbeing: managing stress, building motivation, "
            "self-care routines, confidence, sleep, work-life balance, and coping strategies. "
            "You are warm, empathetic, and non-judgmental."
        ),
        "off_topic_rule": (
            "When the student asks for detailed academic tutoring, gently redirect: "
            "say 'That sounds like an academic question. The Academic Agent would give you "
            "the best help there. I am here to support how you are feeling.'"
        ),
        "persona_rule": "Be warm, empathetic, and supportive. Validate feelings before offering strategies.",
    },
    "social": {
        "identity": "Social Agent",
        "scope_desc": (
            "You help the student with social and community aspects of university life: "
            "finding study groups, building peer connections, networking, campus activities, collaborative "
            "learning, and navigating Pakistani university social dynamics."
        ),
        "off_topic_rule": (
            "When the student asks for detailed academic tutoring, redirect them to the Academic Agent. "
            "When they need emotional support, redirect to the Wellness Agent."
        ),
        "persona_rule": "Be friendly and encouraging. Emphasize community, collaboration, and belonging.",
    },
    "coordinator": {
        "identity": "Coordinator Agent",
        "scope_desc": (
            "You are the central coordinator with access to all student context (academic, social, "
            "wellness, and Digital Twin data). You help with holistic questions, weekly summaries, "
            "progress reports, and any question that spans multiple domains."
        ),
        "off_topic_rule": (
            "As Coordinator, you can answer nearly any student-support question. "
            "For deep academic tutoring, prefer the Academic Agent. "
            "For serious mental health concerns, suggest speaking with a human counselor."
        ),
        "persona_rule": (
            "Be holistic and strategic. Give the student a bird's-eye view of their situation "
            "and connect insights across academic, social, and wellness domains."
        ),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# PromptPackage
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PromptPackage:
    state: StudentState
    persona: str
    system_instruction: str
    user_message: str
    needs_pgvector: bool
    ctx_snapshot: dict


# ─────────────────────────────────────────────────────────────────────────────
# State determination
# ─────────────────────────────────────────────────────────────────────────────

def determine_state(ctx: StudentContext) -> StudentState:
    effective_bloom = ctx.effective_bloom
    if ctx.p_mastery < 0.4 or ctx.language_barrier_risk > 0.6:
        return "STRUGGLING"
    if ctx.p_mastery > 0.7 or effective_bloom >= 4:
        return "INTELLIGENT"
    return "DEVELOPING"


# ─────────────────────────────────────────────────────────────────────────────
# Prompt building helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bloom_label(level: int) -> str:
    return BLOOM_LABELS.get(max(1, min(6, level)), "Remember")


def _vark_label(styles: dict) -> str:
    if not styles:
        return "mixed"
    return max(styles, key=lambda k: styles.get(k, 0), default="mixed")


def _urdu_note(ctx: StudentContext) -> str:
    if ctx.needs_urdu_support:
        return (
            "Language support: When introducing technical terms, optionally add the Urdu equivalent "
            "in parentheses — e.g., \"algorithm (الگورتھم)\". Keep language simple and clear."
        )
    return ""


def _cognitive_rules_summary(rules: dict) -> str:
    if not rules:
        return ""
    parts = []
    if rules.get("chunking"):
        parts.append(f"chunking={rules['chunking']}")
    if rules.get("pacing"):
        parts.append(f"pacing={rules['pacing']}")
    if rules.get("languageSupport"):
        parts.append(f"language_support={rules['languageSupport']}")
    if rules.get("last_notes"):
        parts.append(f"counselor_note={rules['last_notes'][:120]}")
    return "Cognitive preferences: " + "; ".join(parts) if parts else ""


def _twin_state_description(ctx: StudentContext) -> str:
    urgency_note = ""
    if ctx.twin_intervention_urgency == "high":
        urgency_note = " ⚠️ HIGH URGENCY — provide immediate, focused support."
    return (
        f"State: {ctx.twin_cognitive_state.replace('_', ' ').title()} | "
        f"Frustration: {int(ctx.twin_frustration * 100)}% | "
        f"Motivation: {int(ctx.twin_motivation * 100)}% | "
        f"Engagement: {ctx.twin_engagement} | "
        f"Learning velocity: {round(ctx.twin_learning_velocity, 2)}{urgency_note}"
    )


def _risk_summary(ctx: StudentContext) -> str:
    at_risk_pct = int(ctx.twin_at_risk * 100)
    correctness_pct = int(ctx.twin_predicted_correctness * 100)
    return (
        f"At-risk score: {at_risk_pct}% | "
        f"Predicted next answer correctness: {correctness_pct}% | "
        f"Recommended agent: {ctx.twin_recommended_agent}"
    )


def _wellness_summary(ctx: StudentContext) -> str:
    return (
        f"30-day stress: {int(ctx.twin_stress_30d * 100)}% | "
        f"Burnout risk: {int(ctx.twin_burnout_risk * 100)}% | "
        f"Social integration: {int(ctx.twin_social_score * 100)}%"
    )


def _rag_section(rag_context: str) -> str:
    if not rag_context:
        return ""
    return f"\n\n═══ RETRIEVED CONTEXT (RAG) ═══\n{rag_context}"


def _episodic_section(memories: list) -> str:
    if not memories:
        return ""
    items = "\n".join(f"  [{i+1}] {m[:400]}" for i, m in enumerate(memories))
    return f"\n\n═══ RELEVANT PAST MEMORIES ═══\n{items}"


def _cross_agent_section(ctx: StudentContext) -> str:
    lines = []
    if ctx.cross_agent_context:
        lines.append(ctx.cross_agent_context)
    if ctx.student_model_summary:
        lines.append(f"Student profile vibe: {ctx.student_model_summary[:300]}")
    if not lines:
        return ""
    return "\n\n═══ CROSS-AGENT SHARED MEMORY ═══\n" + "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main: Build Prompt Package
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt_package(
    ctx: StudentContext,
    user_message: str,
    student_name: str = "the student",
    agent_type: str = "coordinator",
    orchestration_context: dict | None = None,
    rag_context: str = "",
) -> PromptPackage:
    """
    Builds a complete, rich system prompt using the full StudentContext.
    No token truncation at this layer — the full prompt is sent to Gemini.
    """
    state           = determine_state(ctx)
    orchestration_context = orchestration_context or {}
    agent_key       = (agent_type or "coordinator").lower()
    agent_info      = _AGENT_SCOPE.get(agent_key, _AGENT_SCOPE["coordinator"])
    effective_bloom = ctx.effective_bloom
    bloom_label     = _bloom_label(effective_bloom)
    vark            = _vark_label(ctx.learning_styles)
    urdu_note       = _urdu_note(ctx)
    cog_rules       = _cognitive_rules_summary(ctx.cognitive_rules)

    # ── Persona based on state ────────────────────────────────────────────────
    if state == "INTELLIGENT":
        persona = "Peer-to-Peer"
        persona_rule = (
            "Be a knowledgeable peer: direct, practical, skip basics. "
            "Use advanced vocabulary appropriate to Bloom level. "
            "Provide complete, nuanced answers."
        )
    elif state == "STRUGGLING":
        persona = "Socratic Tutor"
        persona_rule = (
            "Start with one guiding question, then scaffold step by step. "
            "Break concepts into small digestible chunks. "
            "Be patient, supportive, and never overwhelming."
        )
    else:
        persona = "Encouraging Coach"
        persona_rule = (
            "Provide a clear explanation followed by one practice hint. "
            "Keep tone warm and encouraging. Be thorough but accessible."
        )

    # ── Build the full system prompt ──────────────────────────────────────────
    system_parts = [
        f"You are the {agent_info['identity']} for LUMINA — an AI-powered student support "
        f"system designed for Pakistani university students.",
        "",
        "═══ YOUR ROLE & SCOPE ═══",
        agent_info["scope_desc"],
        "",
        "OFF-TOPIC HANDLING:",
        agent_info["off_topic_rule"],
        "",
        "═══ STUDENT PROFILE ═══",
        f"Name: {student_name} | University: {ctx.university or 'Pakistani University'} | Major: {ctx.major or 'Unknown'}",
        f"Bloom Level: {effective_bloom}/6 ({bloom_label}) | Study Pace: {ctx.study_pace} | Learning Style: {vark}",
        f"Language Preference: {ctx.language_preference} | Language Barrier Risk: {int(ctx.language_barrier_risk * 100)}%",
    ]

    if urdu_note:
        system_parts.append(urdu_note)
    if cog_rules:
        system_parts.append(cog_rules)

    system_parts += [
        "",
        "═══ LIVE COGNITIVE STATE (Digital Twin) ═══",
        _twin_state_description(ctx),
        _risk_summary(ctx),
        "",
        "═══ WELLNESS STATE ═══",
        _wellness_summary(ctx),
        f"Current mood: {ctx.effective_mood} | Sentiment: {ctx.effective_sentiment}",
    ]

    cross_agent = _cross_agent_section(ctx)
    if cross_agent:
        system_parts.append(cross_agent)

    episodic = _episodic_section(ctx.episodic_memories)
    if episodic:
        system_parts.append(episodic)

    if rag_context:
        system_parts.append(_rag_section(rag_context))

    system_parts += [
        "",
        "═══ RESPONSE RULES ═══",
        f"1. Stay within your agent scope. {agent_info['off_topic_rule'][:120]}",
        f"2. Persona: {persona}. {persona_rule}",
        f"3. {agent_info['persona_rule']}",
        f"4. Bloom level {effective_bloom}/6: {'use advanced concepts' if effective_bloom >= 4 else 'use simple, concrete explanations'}.",
        "5. Give COMPLETE answers — never end mid-sentence or cut off.",
        "6. Reference past context from memories when relevant.",
        "7. If frustration > 60% or motivation < 40%, be extra patient and encouraging.",
        "8. Keep responses focused and practical for Pakistani university context.",
        "9. Speak as this specific agent and stay in character. Naturally reflect the student's "
        "current learning status (their topic, Bloom level, mastery) and their mind/mood status "
        "so they feel understood — do not dump raw numbers, weave it into the conversation.",
        "10. If the question is clearly outside your scope, do NOT attempt to answer it. Say plainly "
        "that this is not something you handle, briefly acknowledge where they are in their learning "
        "and how they seem to be feeling, then name the exact agent they should talk to "
        "(Academic, Wellness, or Social) and invite them back when ready.",
        "",
        "═══ FORMATTING RULES (MUST FOLLOW) ═══",
        "Write every response in natural flowing paragraphs.",
        "Never use bullet points, dashes (-), asterisks (*), numbered lists, or markdown headers.",
        "Do not use bold (**text**) or italic (*text*) markdown formatting.",
        "Write as if you are speaking directly to the student in a warm, natural conversation.",
        "If you need to list steps, write them as sentences in a paragraph: 'First... then... after that...'",
    ]

    system_instruction = "\n".join(system_parts)

    # needs_pgvector when student is struggling and low practice
    needs_pgvector = ctx.p_mastery < 0.4 and ctx.practice_count < 3

    ctx_snapshot = {
        "user_id":           ctx.user_id,
        "skill_name":        ctx.skill_name,
        "p_mastery":         round(ctx.p_mastery, 3),
        "bloom_level":       effective_bloom,
        "twin_state":        ctx.twin_cognitive_state,
        "twin_frustration":  round(ctx.twin_frustration, 2),
        "twin_at_risk":      round(ctx.twin_at_risk, 2),
        "language_risk":     round(ctx.language_barrier_risk, 2),
        "mood":              ctx.effective_mood,
        "state":             state,
        "persona":           persona,
        "needs_pgvector":    needs_pgvector,
        "episodic_count":    len(ctx.episodic_memories),
        "agent_type":        agent_key,
    }

    logger.info(
        "PromptPackage | agent=%s state=%s persona=%s bloom=%d "
        "p_mastery=%.2f twin_state=%s at_risk=%.2f episodic=%d",
        agent_key, state, persona, effective_bloom,
        ctx.p_mastery, ctx.twin_cognitive_state,
        ctx.twin_at_risk, len(ctx.episodic_memories),
    )

    return PromptPackage(
        state=state,
        persona=persona,
        system_instruction=system_instruction,
        user_message=user_message,
        needs_pgvector=needs_pgvector,
        ctx_snapshot=ctx_snapshot,
    )


# ── kept for backwards compat (imported by agent_router) ─────────────────────
PROMPT_TEMPLATE_A = "Peer-to-Peer: {name}, {skill_name}, bloom={bloom_level}, mood={mood}, state={cognitive_state}"
PROMPT_TEMPLATE_B = "Socratic Tutor: {name}, {skill_name}, lang_risk={lang_risk_pct}%, style={dominant_style}{urdu_note}"
PROMPT_TEMPLATE_C = "Encouraging Coach: {name}, {skill_name}, pace={study_pace}{urdu_note}"

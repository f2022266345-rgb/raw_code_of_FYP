"""Agent registry — identity, scope, guardrails, and off-topic detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Off-topic keyword detection (hard redirect BEFORE calling the LLM)
# ─────────────────────────────────────────────────────────────────────────────

_WELLNESS_KEYWORDS = frozenset({
    "stress", "stressed", "anxiety", "anxious", "panic", "depression", "depressed",
    "sad", "mental health", "mental", "wellness", "overwhelmed", "burnout",
    "crying", "hopeless", "worthless", "suicid", "harming myself", "can't cope",
    "emotionally", "feeling down", "low mood", "exhausted mentally",
})

_SOCIAL_KEYWORDS = frozenset({
    "friends", "friend", "lonely", "alone", "isolation", "peer", "study group",
    "community", "networking", "campus", "social", "club", "extracurricular",
    "team", "group project", "collaboration",
})

_ACADEMIC_KEYWORDS = frozenset({
    "study", "exam", "quiz", "assignment", "homework", "explain", "solve",
    "calculate", "formula", "concept", "theory", "learn", "course", "lecture",
    "notes", "textbook", "practice", "math", "physics", "chemistry", "biology",
    "programming", "code", "algorithm", "grade", "gpa", "topic", "chapter",
    "bloom", "skill", "mastery", "weak area", "revision",
})


def _contains_any(text: str, keywords: frozenset) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def detect_off_topic(agent_type: str, message: str) -> Optional[str]:
    """
    Hard pre-LLM check. Returns a redirect message string if the message
    is clearly off-topic for the given agent, else returns None.

    This runs BEFORE calling the LLM so we never waste an API call on a
    clear scope violation.
    """
    if not message:
        return None

    lower = message.lower()
    is_wellness  = _contains_any(lower, _WELLNESS_KEYWORDS)
    is_social    = _contains_any(lower, _SOCIAL_KEYWORDS)
    is_academic  = _contains_any(lower, _ACADEMIC_KEYWORDS)

    if agent_type == "academic":
        if is_wellness and not is_academic:
            return (
                "I can hear that you're going through a tough time emotionally. "
                "I'm the Academic Agent and I want to make sure you get the right support — "
                "please switch to the **Wellness Agent** who is better equipped to help with what you're feeling. "
                "I'm here whenever you're ready to work on academics together."
            )

    elif agent_type == "wellness":
        if is_academic and not is_wellness:
            # Only hard-redirect for deep tutoring requests, not casual academic mentions
            deep_tutoring = any(phrase in lower for phrase in (
                "solve this", "explain this concept", "homework help",
                "teach me how to", "step by step solution", "calculate",
            ))
            if deep_tutoring:
                return (
                    "That sounds like a great academic question! "
                    "I'm the Wellness Agent focused on your mental and emotional wellbeing. "
                    "For detailed academic help, please switch to the **Academic Agent**. "
                    "I'm here if you want to talk about how you're feeling."
                )

    elif agent_type == "social":
        if not is_social and not is_wellness:
            deep_academic = any(phrase in lower for phrase in (
                "solve this", "explain this theorem", "calculus problem",
                "i don't understand the formula",
            ))
            if deep_academic:
                return (
                    "That's a detailed academic question — the **Academic Agent** would be perfect for that! "
                    "I'm the Social Agent focused on your relationships, study groups, and campus life. "
                    "Come back to me when you want help connecting with peers or finding study partners."
                )

    return None  # no redirect needed


# ─────────────────────────────────────────────────────────────────────────────
# AgentProfile
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentProfile:
    key: str
    name: str
    role: str
    guardrails: str


ACADEMIC_HANDOFF_TEXT = (
    "I can hear that you're going through a tough time. I'm the Academic Agent — "
    "please switch to the Wellness Agent for emotional support. "
    "I'm here for you academically whenever you're ready."
)


def get_agent_profile(agent_type: str) -> AgentProfile:
    normalized = (agent_type or "coordinator").lower()

    if normalized == "academic":
        return AgentProfile(
            key="academic",
            name="Academic Support Agent",
            role="Academic",
            guardrails=(
                "\nAgent Identity: You are the LUMINA Academic Support Agent. "
                "Your scope: academic concepts, study strategies, skill gaps, exam prep, "
                "course planning, Bloom-level content, and subject tutoring (math, science, CS, etc.). "
                "You NEVER provide mental health counseling. If the student expresses emotional distress, "
                f"respond ONLY with: \"{ACADEMIC_HANDOFF_TEXT}\""
            ),
        )

    if normalized == "wellness":
        return AgentProfile(
            key="wellness",
            name="Wellness Agent",
            role="Wellness",
            guardrails=(
                "\nAgent Identity: You are the LUMINA Wellness Agent. "
                "Your scope: stress, anxiety, burnout, motivation, self-care, sleep, confidence, "
                "work-life balance, and emotional support. "
                "You are warm, empathetic, and non-judgmental. "
                "You do NOT provide deep academic tutoring. "
                "If asked for detailed academic content, redirect to the Academic Agent."
            ),
        )

    if normalized == "social":
        return AgentProfile(
            key="social",
            name="Social Agent",
            role="Social",
            guardrails=(
                "\nAgent Identity: You are the LUMINA Social Agent. "
                "Your scope: study groups, peer connections, networking, campus life, "
                "Pakistani university social dynamics, collaborative learning. "
                "You do NOT provide deep academic tutoring or mental health counseling. "
                "Redirect detailed academic questions to Academic Agent, "
                "emotional crises to Wellness Agent."
            ),
        )

    return AgentProfile(
        key="coordinator",
        name="Coordinator Agent",
        role="Coordinator",
        guardrails=(
            "\nAgent Identity: You are the LUMINA Coordinator Agent. "
            "You have full access to all student context (academic, social, wellness, Digital Twin). "
            "You provide holistic guidance, weekly summaries, progress reports, and cross-domain advice. "
            "You route complex or domain-specific questions to the appropriate specialist agent."
        ),
    )


def build_crewai_agent(agent_type: str):
    try:
        from crewai import Agent
    except Exception:
        return None
    profile = get_agent_profile(agent_type)
    return Agent(role=profile.role, goal=profile.guardrails, backstory=f"{profile.name} for Lumina.", verbose=False)


def build_langgraph_agent(agent_type: str):
    try:
        from langgraph.graph import StateGraph
    except Exception:
        return None
    _ = agent_type
    return StateGraph()

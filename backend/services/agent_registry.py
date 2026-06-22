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


# ─────────────────────────────────────────────────────────────────────────────
# Personalization helpers — let each agent "mimic" awareness of the student's
# live learning status and mind status when it redirects.
# ─────────────────────────────────────────────────────────────────────────────

AGENT_DISPLAY = {
    "academic": "Academic Agent",
    "wellness": "Wellness Agent",
    "social": "Social Agent",
    "coordinator": "Coordinator Agent",
}

_BLOOM_LABELS = {
    1: "Remember", 2: "Understand", 3: "Apply",
    4: "Analyse", 5: "Evaluate", 6: "Create",
}


def _learning_snapshot(ctx) -> str:
    """A short, human sentence describing what the student is currently learning."""
    if ctx is None:
        return ""
    try:
        bloom = int(getattr(ctx, "effective_bloom", 1) or 1)
        bloom = max(1, min(6, bloom))
        mastery = int(round(float(getattr(ctx, "p_mastery", 0.0) or 0.0) * 100))
        skill = (getattr(ctx, "skill_name", "") or "").strip()
        label = _BLOOM_LABELS.get(bloom, "Remember")
        if skill and skill.lower() not in ("general", "unknown", "none"):
            return (
                f"Right now you're working on {skill} at Bloom level {bloom} ({label}), "
                f"sitting at about {mastery}% mastery"
            )
        return f"Right now you're at Bloom level {bloom} ({label}), around {mastery}% mastery"
    except Exception:
        return ""


def _mind_snapshot(ctx) -> str:
    """A short, human sentence describing the student's current mind / mood status."""
    if ctx is None:
        return ""
    try:
        mood = (getattr(ctx, "effective_mood", "") or "").strip()
        frustration = int(round(float(getattr(ctx, "twin_frustration", 0.0) or 0.0) * 100))
        motivation = int(round(float(getattr(ctx, "twin_motivation", 0.0) or 0.0) * 100))
        bits = []
        if mood and mood.lower() not in ("neutral", "unknown", "none", ""):
            bits.append(f"your mood reads as {mood.lower()}")
        if frustration >= 60:
            bits.append(f"frustration is running high (~{frustration}%)")
        elif motivation and motivation < 40:
            bits.append(f"motivation looks low (~{motivation}%)")
        if not bits:
            return ""
        return "and " + " and ".join(bits)
    except Exception:
        return ""


def _personalized_redirect(agent_type: str, target_agent: str, ctx, student_name: str) -> str:
    """
    Build a redirect that (1) makes clear the question is outside this agent's
    scope, (2) mimics the agent by referencing the student's live learning +
    mind status, and (3) points them to the right agent to talk to.
    """
    here = AGENT_DISPLAY.get(agent_type, "this agent")
    there = AGENT_DISPLAY.get(target_agent, "the right specialist")
    name = (student_name or "").strip()
    greeting = f"{name}, " if name and name.lower() != "the student" else ""

    learning = _learning_snapshot(ctx)
    mind = _mind_snapshot(ctx)
    status_line = ""
    if learning or mind:
        status_line = " " + " ".join(filter(None, [learning + ("," if learning and mind else ""), mind])).strip()
        if status_line and not status_line.endswith((".", "!")):
            status_line += "."

    # What the target agent is for, phrased warmly.
    target_focus = {
        "wellness": "how you're feeling and your emotional wellbeing",
        "academic": "the actual studying, concepts and problem-solving",
        "social": "friends, study groups and campus life",
        "coordinator": "the bigger picture across all areas",
    }.get(target_agent, "this area")

    return (
        f"{greeting}as your {here}, this question is really about {target_focus}, "
        f"which sits outside what I focus on, so it's not something I'm the right one to answer.{status_line} "
        f"Please talk to the {there} for this, as they're properly equipped to help you here, "
        f"and I'll be right with you to pick things up the moment you're ready to continue."
    )


def build_redirect(agent_type: str, target_agent: str, ctx=None, student_name: str = "") -> str:
    """Public helper to build a personalized scope-redirect message (mimics the
    agent and references the student's live learning + mind status)."""
    return _personalized_redirect(agent_type, target_agent, ctx, student_name)


def detect_off_topic_target(agent_type: str, message: str) -> Optional[str]:
    """
    Hard pre-LLM scope check. Returns the agent key the student SHOULD be talking
    to (e.g. "wellness" / "academic") if the message is clearly off-topic for the
    current agent, else None.
    """
    if not message:
        return None

    lower = message.lower()
    is_wellness  = _contains_any(lower, _WELLNESS_KEYWORDS)
    is_social    = _contains_any(lower, _SOCIAL_KEYWORDS)
    is_academic  = _contains_any(lower, _ACADEMIC_KEYWORDS)

    if agent_type == "academic":
        if is_wellness and not is_academic:
            return "wellness"

    elif agent_type == "wellness":
        if is_academic and not is_wellness:
            deep_tutoring = any(phrase in lower for phrase in (
                "solve this", "explain this concept", "homework help",
                "teach me how to", "step by step solution", "calculate",
            ))
            if deep_tutoring:
                return "academic"

    elif agent_type == "social":
        if not is_social and not is_wellness:
            deep_academic = any(phrase in lower for phrase in (
                "solve this", "explain this theorem", "calculus problem",
                "i don't understand the formula",
            ))
            if deep_academic:
                return "academic"

    return None


def detect_off_topic(
    agent_type: str,
    message: str,
    ctx=None,
    student_name: str = "",
) -> Optional[str]:
    """
    Hard pre-LLM check. Returns a personalized redirect message if the message is
    clearly off-topic for the given agent, else None.

    When `ctx` (a StudentContext) is supplied, the redirect mimics the agent by
    weaving in the student's live learning status and mind/mood status. Runs
    BEFORE the LLM call so we never spend an API request on a clear scope miss.
    """
    target = detect_off_topic_target(agent_type, message)
    if not target:
        return None
    return _personalized_redirect(agent_type, target, ctx, student_name)


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

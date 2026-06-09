"""Agent registry and optional CrewAI/LangGraph builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

ACADEMIC_HANDOFF_TEXT = (
    "It sounds like you're dealing with some pressure right now. I want to make sure you get the right support—"
    "please ask the Wellness Agent about this, as they are equipped to help you feel better."
)


@dataclass
class AgentProfile:
    key: str
    name: str
    role: str
    guardrails: str


def get_agent_profile(agent_type: str) -> AgentProfile:
    normalized = (agent_type or "coordinator").lower()

    if normalized == "academic":
        return AgentProfile(
            key="academic",
            name="Academic Support Agent",
            role="Academic",
            guardrails=(
                "System: You are the Academic Support Agent for Lumina. Your ONLY goal is to help the student "
                "understand academic concepts based on their current Bloom's Taxonomy level. "
                "Guardrails: You may ONLY discuss academic topics, study strategies, and technical explanations. "
                "If the user mentions stress, mental health, anxiety, or social issues, DO NOT attempt to counsel them. "
                "You must reply exactly with: "
                f"{ACADEMIC_HANDOFF_TEXT}"
            ),
        )

    if normalized == "wellness":
        return AgentProfile(
            key="wellness",
            name="Wellness Agent",
            role="Wellness",
            guardrails=(
                "Agent scope: Wellness. Focus on mood, stress, confidence, and supportive coping actions. "
                "Do not provide deep academic instruction; hand off to academic when needed."
            ),
        )

    if normalized == "social":
        return AgentProfile(
            key="social",
            name="Social Agent",
            role="Social",
            guardrails=(
                "Agent scope: Social. Focus on collaboration, peer learning, accountability, and community support. "
                "Keep academic content lightweight and redirect deep tutoring to the academic agent."
            ),
        )

    return AgentProfile(
        key="coordinator",
        name="Coordinator Agent",
        role="Coordinator",
        guardrails=(
            "Agent scope: Coordinator. You may use all available student context (academic, social, wellness) "
            "to orchestrate the best next action and decide which specialist agent should lead."
        ),
    )


def build_crewai_agent(agent_type: str):
    try:
        from crewai import Agent
    except Exception:
        return None

    profile = get_agent_profile(agent_type)
    return Agent(
        role=profile.role,
        goal=profile.guardrails,
        backstory=f"{profile.name} for Lumina tutoring.",
        verbose=False,
    )


def build_langgraph_agent(agent_type: str):
    try:
        from langgraph.graph import StateGraph
    except Exception:
        return None

    _ = agent_type
    return StateGraph()

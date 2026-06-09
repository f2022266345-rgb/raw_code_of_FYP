"""Simple agent class wrappers for the five agent roles.

These provide a clean interface for generating responses and encapsulate
role-specific guardrails (Academic, Wellness, Social, Coordinator, Router).
"""
from __future__ import annotations

from typing import Optional

from .agent_registry import get_agent_profile, ACADEMIC_HANDOFF_TEXT
from .gemini_agent import call_gemini


class BaseAgent:
    def __init__(self, agent_type: str, db=None):
        self.profile = get_agent_profile(agent_type)
        self.db = db

    def generate(self, *, system_instruction: str, user_message: str, **kwargs) -> str:
        # Default behavior: forward to call_gemini
        return call_gemini(
            system_instruction=system_instruction,
            user_message=user_message,
            db=self.db,
            **kwargs,
        )


class AcademicAgent(BaseAgent):
    def generate(self, *, system_instruction: str, user_message: str, user_id: Optional[str] = None, **kwargs) -> str:
        text = (user_message or "").lower()
        wellness_keywords = {"stress","anxiety","depression","mental","overwhelmed","burnout"}
        if any(k in text for k in wellness_keywords):
            return ACADEMIC_HANDOFF_TEXT
        return call_gemini(system_instruction=system_instruction, user_message=user_message, db=self.db, user_id=user_id, **kwargs)


class WellnessAgent(BaseAgent):
    pass


class SocialAgent(BaseAgent):
    pass


class CoordinatorAgent(BaseAgent):
    pass


def get_agent_instance(agent_type: str, db=None) -> BaseAgent:
    at = (agent_type or "coordinator").lower()
    if at == "academic":
        return AcademicAgent(at, db=db)
    if at == "wellness":
        return WellnessAgent(at, db=db)
    if at == "social":
        return SocialAgent(at, db=db)
    return CoordinatorAgent(at, db=db)

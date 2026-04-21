"""
services/chat_service.py
------------------------
LLM-powered chat service for all AI agents.

Uses OpenAI GPT-4o with per-agent system prompts that are:
- Bloom-taxonomy-aware (adapts depth to student's level)
- Culturally aware (supports Urdu-medium students)
- Context-injected (uses student profile from DB)
"""

from __future__ import annotations

import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Lazy import — OpenAI client only initialized when first called
_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set — chat will use fallback responses.")
                return None
            _client = OpenAI(api_key=api_key)
        except Exception as e:
            logger.error("Failed to initialize OpenAI client: %s", e)
            return None
    return _client


# ── Bloom level labels ────────────────────────────────────────────────────────

_BLOOM_LABELS = {
    1: "Remember (recall facts and basic concepts)",
    2: "Understand (explain ideas or concepts)",
    3: "Apply (use information in new situations)",
    4: "Analyze (draw connections among ideas)",
    5: "Evaluate (justify a decision or course of action)",
    6: "Create (produce new or original work)",
}


def _build_system_prompt(agent_type: str, student_context: Dict[str, Any]) -> str:
    """Constructs a context-rich system prompt for the specified agent type."""

    name = student_context.get("name", "Student")
    major = student_context.get("major", "Computer Science")
    bloom_level = student_context.get("bloom_level", 2)
    language_preference = student_context.get("language_preference", "english-only")
    language_barrier_risk = student_context.get("language_barrier_risk", 0.2)
    stress_level = student_context.get("stress_level", 4)
    bloom_label = _BLOOM_LABELS.get(bloom_level, _BLOOM_LABELS[2])

    # Language support instruction
    lang_instruction = ""
    if language_preference in ("urdu-primary", "bilingual") or language_barrier_risk >= 0.6:
        lang_instruction = (
            "\n- This student may struggle with English technical terms. "
            "When introducing a new concept, optionally provide the Urdu equivalent in parentheses "
            "(e.g., 'loop (لوپ)'). Keep sentences short and clear."
        )

    base = f"""You are an AI educational assistant at Lumina AI Academy, specifically acting as the {agent_type.upper()} AGENT.

Student Context:
- Name: {name}
- Major: {major}
- Current Bloom Level: {bloom_level} — {bloom_label}
- Language Barrier Risk: {language_barrier_risk:.0%}
- Stress Level: {stress_level}/10

Core Instructions:
- Always address the student by their first name.
- Match your explanation depth to their Bloom level {bloom_level}/6. Do NOT explain things that are too advanced.
- Keep responses concise (max 4 sentences unless asked to elaborate).
- Be warm, encouraging, and culturally sensitive.{lang_instruction}"""

    agent_prompts = {
        "academic": f"""{base}

As the ACADEMIC AGENT:
- Focus on learning content, skill mastery, and study strategies.
- Suggest practice problems calibrated to Bloom level {bloom_level}.
- If the student is struggling, drop to a simpler explanation before re-attempting the harder concept.
- Reference specific skills and knowledge areas relevant to {major}.""",

        "wellness": f"""{base}

As the WELLNESS AGENT:
- The student's stress level is {stress_level}/10 — {"HIGH, this is a priority" if stress_level >= 7 else "manageable"}.
- Focus on emotional support, stress management, and mental health.
- Suggest breathing exercises, breaks, or mindfulness techniques when stress is high.
- NEVER diagnose or provide medical advice. If a student expresses self-harm thoughts, respond with crisis resources immediately.
- Be empathetic and validate feelings before offering solutions.""",

        "social": f"""{base}

As the SOCIAL AGENT:
- Focus on peer collaboration, study groups, and social engagement.
- Suggest specific collaboration strategies relevant to {major}.
- Help the student overcome isolation or boredom.
- Encourage healthy social connections while respecting boundaries.""",

        "coordinator": f"""{base}

As the COORDINATOR AGENT (Master Orchestrator):
- You have full visibility into all other agents: Academic, Wellness, and Social.
- Synthesize insights from all agents to give holistic guidance.
- Decide which aspect (academic, social, or wellness) needs attention most urgently.
- Route the student's concerns to the most relevant agent perspective.
- Be decisive and strategic in your recommendations.""",

        "tutor": f"""{base}

As the TUTOR AGENT:
- Deliver personalized explanations using the Socratic method when appropriate.
- Provide step-by-step worked examples for {major}-relevant problems.
- Calibrate hint depth to Bloom level {bloom_level}: at level 1-2, be more explicit; at level 4-6, ask guiding questions.
- Support Urdu-medium learners by breaking down technical English jargon.""",
    }

    return agent_prompts.get(agent_type, agent_prompts["coordinator"])


def generate_agent_response(
    agent_type: str,
    message: str,
    student_context: Dict[str, Any],
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Calls OpenAI to generate a response from the specified agent.

    Args:
        agent_type: One of 'academic', 'wellness', 'social', 'coordinator', 'tutor'
        message: The student's latest message
        student_context: Dict with name, major, bloom_level, etc.
        chat_history: List of {"role": "user"/"assistant", "content": "..."} dicts

    Returns:
        Agent response string, or a fallback string on error.
    """
    client = _get_client()
    if client is None:
        return _fallback_response(agent_type, message)

    system_prompt = _build_system_prompt(agent_type, student_context)

    messages = [{"role": "system", "content": system_prompt}]

    # Add recent chat history (last 6 turns to stay within context limits)
    if chat_history:
        messages.extend(chat_history[-6:])

    # Add the current message
    messages.append({"role": "user", "content": message})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",          # Cost-efficient, fast, excellent for tutoring
            messages=messages,
            temperature=0.7,
            max_tokens=512,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error("OpenAI API error in agent '%s': %s", agent_type, e)
        return _fallback_response(agent_type, message)


def _fallback_response(agent_type: str, message: str) -> str:
    """Returns a graceful fallback when the LLM is unavailable."""
    fallbacks = {
        "academic": "I'm here to help with your studies! Could you tell me more about what you're working on so I can guide you better?",
        "wellness": "I hear you. Taking care of your mental health is just as important as academics. How are you feeling right now?",
        "social": "Building connections is so important! Have you considered joining a study group this week?",
        "coordinator": "I'm analyzing your progress across all areas. Let me know what's on your mind and I'll direct you to the right support.",
        "tutor": "Great question! Let's break this down step by step. What part are you finding most challenging?",
    }
    return fallbacks.get(agent_type, fallbacks["coordinator"])

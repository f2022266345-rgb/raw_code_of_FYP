from app.graph.state import GraphState
from services.gemini_agent import _get_gemini_client, _iter_model_candidates
from google.genai import types

async def generate_academic_plan(state: GraphState) -> dict:
    client = _get_gemini_client()
    profile = state.get("student_profile", {})
    
    prompt = f"""You are a pedagogical expert.
Based on this student profile: {profile}
Create a robust academic study plan for the semester."""
    
    if not client:
        return {"academic_plan": "Service unavailable."}
        
    try:
        response = client.models.generate_content(
            model=_iter_model_candidates()[0],
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7)
        )
        return {"academic_plan": response.text}
    except Exception as e:
        return {"academic_plan": f"Error: {e}"}

async def generate_social_plan(state: GraphState) -> dict:
    client = _get_gemini_client()
    profile = state.get("student_profile", {})
    
    prompt = f"""You are a campus life mentor.
Based on this student profile: {profile}
Create a social engagement and extracurricular plan."""
    
    if not client:
        return {"social_plan": "Service unavailable."}
        
    try:
        response = client.models.generate_content(
            model=_iter_model_candidates()[0],
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7)
        )
        return {"social_plan": response.text}
    except Exception as e:
        return {"social_plan": f"Error: {e}"}

async def generate_wellness_plan(state: GraphState) -> dict:
    client = _get_gemini_client()
    profile = state.get("student_profile", {})
    
    prompt = f"""You are a wellness and mental health counselor.
Based on this student profile: {profile}
Create a wellness and stress-management plan."""
    
    if not client:
        return {"wellness_plan": "Service unavailable."}
        
    try:
        response = client.models.generate_content(
            model=_iter_model_candidates()[0],
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7)
        )
        return {"wellness_plan": response.text}
    except Exception as e:
        return {"wellness_plan": f"Error: {e}"}

async def synthesize_plan_node(state: GraphState) -> dict:
    client = _get_gemini_client()
    academic = state.get("academic_plan", "")
    social = state.get("social_plan", "")
    wellness = state.get("wellness_plan", "")
    
    prompt = f"""You are the master coordinator.
Merge the following plans into a single cohesive curriculum for the student.

Academic Plan:
{academic}

Social Plan:
{social}

Wellness Plan:
{wellness}

Return the final cohesive curriculum."""
    
    if not client:
        return {"final_plan": "Service unavailable."}
        
    try:
        response = client.models.generate_content(
            model=_iter_model_candidates()[0],
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.5)
        )
        return {"final_plan": response.text}
    except Exception as e:
        return {"final_plan": f"Error: {e}"}

async def human_support_node(state: GraphState) -> dict:
    return {"final_plan": "ESCALATION: Execution halted. Case routed to Human Support Services due to critical severity."}

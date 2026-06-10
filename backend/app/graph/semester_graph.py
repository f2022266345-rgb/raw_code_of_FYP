import json
from typing import TypedDict, Dict, Any, List
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage

from db import SessionLocal, BktSkillMasteryORM, InteractionLogORM, InitialProfileORM, ProgressSnapshotORM
from services.gemini_agent import _get_openai_client, _iter_model_candidates
from datetime import datetime, timedelta, timezone

class SemesterState(TypedDict):
    user_id: str
    data: Dict[str, Any]
    analysis: str
    is_critical: bool

async def ingestion_node(state: SemesterState) -> dict:
    user_id = state["user_id"]
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        two_weeks_ago = now - timedelta(days=14)
        
        logs = db.query(InteractionLogORM).filter(
            InteractionLogORM.user_id == user_id,
            InteractionLogORM.created_at >= two_weeks_ago
        ).all()
        
        bkt = db.query(BktSkillMasteryORM).filter(
            BktSkillMasteryORM.user_id == user_id
        ).all()
        
        grades = {s.skill_name: s.p_mastery for s in bkt}
        attendance = len(logs) / 14.0 if len(logs) > 0 else 0.0
        
        data = {
            "grades": grades,
            "attendance_rate": min(attendance, 1.0),
            "total_interactions_last_14_days": len(logs)
        }
        
        snapshot = ProgressSnapshotORM(
            user_id=user_id,
            grades=grades,
            attendance_rate=min(attendance, 1.0),
            engagement_metrics={"total_interactions": len(logs)},
            embedding=[0.0] * 1536
        )
        db.add(snapshot)
        db.commit()
        
        return {"data": data}
    finally:
        db.close()

async def analysis_node(state: SemesterState) -> dict:
    client = _get_openai_client()
    data = state.get("data", {})
    
    prompt = f"""
    You are an automated academic evaluator.
    Analyze the following 14-day student progress data:
    {json.dumps(data, indent=2)}
    
    Determine if the student is improving or degrading. 
    If they are failing across the board (e.g., p_mastery < 0.2, zero attendance), set "is_critical": true.
    Otherwise, if they are doing well and improving, set "is_critical": false.
    
    Respond STRICTLY with valid JSON in this format:
    {{"analysis": "your reasoning", "is_critical": true/false}}
    """
    
    if not client:
        return {"analysis": "Service unavailable", "is_critical": False}
        
    try:
        response = client.chat.completions.create(
            model=_iter_model_candidates()[0],
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        
        return {
            "analysis": result.get("analysis", ""),
            "is_critical": result.get("is_critical", False)
        }
    except Exception as e:
        return {"analysis": str(e), "is_critical": False}

async def escalation_node(state: SemesterState) -> dict:
    user_id = state["user_id"]
    db = SessionLocal()
    try:
        profile = db.query(InitialProfileORM).filter(InitialProfileORM.user_id == user_id).first()
        if profile:
            # Flag for human intervention in JSON or DB
            if not profile.user_profile:
                profile.user_profile = {}
            profile.user_profile["human_intervention_required"] = True
            profile.user_profile["intervention_reason"] = state.get("analysis", "Critical degradation")
            db.commit()
        return {}
    finally:
        db.close()

async def update_bloom_node(state: SemesterState) -> dict:
    user_id = state["user_id"]
    db = SessionLocal()
    try:
        profile = db.query(InitialProfileORM).filter(InitialProfileORM.user_id == user_id).first()
        if profile and profile.bloom_level is not None:
            if profile.bloom_level < 6:
                profile.bloom_level += 1
            db.commit()
        return {}
    finally:
        db.close()

def critical_adjust_gateway(state: SemesterState) -> str:
    if state.get("is_critical"):
        return "escalation"
    return "update_bloom"

builder = StateGraph(SemesterState)

builder.add_node("ingestion", ingestion_node)
builder.add_node("analysis", analysis_node)
builder.add_node("escalation", escalation_node)
builder.add_node("update_bloom", update_bloom_node)

builder.add_edge(START, "ingestion")
builder.add_edge("ingestion", "analysis")

builder.add_conditional_edges(
    "analysis",
    critical_adjust_gateway,
    {
        "escalation": "escalation",
        "update_bloom": "update_bloom"
    }
)

builder.add_edge("escalation", END)
builder.add_edge("update_bloom", END)

semester_graph = builder.compile()

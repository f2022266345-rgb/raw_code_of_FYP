from app.graph.state import GraphState
from db import SessionLocal
from services.context_retriever import get_student_context

async def gateway_node(state: GraphState) -> dict:
    user_id = state.get("user_id", "")
    message = state["messages"][-1].content if state.get("messages") else ""
    db = SessionLocal()
    try:
        ctx = get_student_context(db, user_id, skill_name="", user_message=message)
        student_context = {
            "vibe_check": getattr(ctx, "student_model_summary", ""),
            "episodic": getattr(ctx, "episodic_memory_summary", ""),
            "bloom_level": ctx.bloom_level,
            "p_mastery": ctx.p_mastery
        }
        return {"student_context": student_context}
    finally:
        db.close()

from sqlalchemy.orm import Session
from services.context_retriever import get_student_context

def fetch_long_term_memory(db: Session, user_id: str, message: str) -> dict:
    ctx = get_student_context(db, user_id, skill_name="", user_message=message)
    return {
        "vibe_check": getattr(ctx, "student_model_summary", ""),
        "episodic": getattr(ctx, "episodic_memory_summary", "")
    }

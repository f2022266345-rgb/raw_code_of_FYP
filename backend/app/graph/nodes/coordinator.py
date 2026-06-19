from app.graph.state import GraphState
from langchain_core.messages import AIMessage
from services.gemini_agent import _get_gemini_client, _iter_model_candidates

async def coordinator_node(state: GraphState) -> dict:
    client = _get_gemini_client()
    if not client:
        return {"active_agent": "academic"}

    user_msg = state["messages"][-1].content if state.get("messages") else ""
    ctx = state.get("student_context", {})
    
    prompt = f"""You are a routing coordinator. 
Student context: {ctx}
User message: {user_msg}
Decide the route. Reply with exactly one word: 'academic', 'social', or 'wellness'."""
    
    try:
        response = client.models.generate_content(
            model=_iter_model_candidates()[0],
            contents=prompt
        )
        agent = response.text.strip().lower()
        if agent not in ["academic", "social", "wellness"]:
            agent = "academic"
        return {"active_agent": agent}
    except Exception:
        return {"active_agent": "academic"}

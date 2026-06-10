from app.graph.state import GraphState
from langchain_core.messages import AIMessage
from services.gemini_agent import _get_openai_client, _iter_model_candidates

async def coordinator_node(state: GraphState) -> dict:
    client = _get_openai_client()
    if not client:
        return {"active_agent": "academic"}

    user_msg = state["messages"][-1].content if state.get("messages") else ""
    ctx = state.get("student_context", {})
    
    prompt = f"""You are a routing coordinator. 
Student context: {ctx}
User message: {user_msg}
Decide the route. Reply with exactly one word: 'academic', 'social', or 'wellness'."""
    
    try:
        response = client.chat.completions.create(
            model=_iter_model_candidates()[0],
            messages=[{"role": "user", "content": prompt}]
        )
        agent = response.choices[0].message.content.strip().lower()
        if agent not in ["academic", "social", "wellness"]:
            agent = "academic"
        return {"active_agent": agent}
    except Exception:
        return {"active_agent": "academic"}

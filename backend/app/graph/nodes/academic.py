from app.graph.state import GraphState
from langchain_core.messages import AIMessage
from services.gemini_agent import _get_openai_client, _iter_model_candidates
from langgraph.store.base import BaseStore
from langchain_core.runnables.config import RunnableConfig
import uuid

async def academic_node(state: GraphState, config: RunnableConfig, store: BaseStore) -> dict:
    client = _get_openai_client()
    user_msg = state["messages"][-1].content if state.get("messages") else ""
    ctx = state.get("student_context", {})
    user_id = state.get("user_id", "default")
    
    namespace = ("academic", user_id)
    # Search past memories via LangGraph Store
    past_items = await store.asearch(namespace)
    past_memories = "\n".join([str(item.value) for item in past_items]) if past_items else "No past memories."
    
    # Store current question for future context
    await store.aput(namespace, str(uuid.uuid4()), {"query": user_msg})
    
    prompt = f"""You are an academic tutor.
Context: {ctx}
Private Academic Memory: {past_memories}
Student asks: {user_msg}
Respond appropriately considering their Bloom's level."""
    
    if not client:
        return {"messages": [AIMessage(content="Academic service unavailable.")]}
        
    try:
        response = client.chat.completions.create(
            model=_iter_model_candidates()[0],
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_msg}]
        )
        return {"messages": [AIMessage(content=response.choices[0].message.content)]}
    except Exception:
        return {"messages": [AIMessage(content="Error generating academic response.")]}

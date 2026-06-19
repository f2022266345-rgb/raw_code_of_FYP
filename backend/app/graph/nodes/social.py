from app.graph.state import GraphState
from langchain_core.messages import AIMessage
from services.gemini_agent import _get_gemini_client, _iter_model_candidates
from langgraph.store.base import BaseStore
from langchain_core.runnables.config import RunnableConfig
import uuid

async def social_node(state: GraphState, config: RunnableConfig, store: BaseStore) -> dict:
    client = _get_gemini_client()
    user_msg = state["messages"][-1].content if state.get("messages") else ""
    user_id = state.get("user_id", "default")
    
    namespace = ("social", user_id)
    past_items = await store.asearch(namespace)
    past_memories = "\n".join([str(item.value) for item in past_items]) if past_items else "No past memories."
    
    await store.aput(namespace, str(uuid.uuid4()), {"query": user_msg})
    
    prompt = f"""You are a friendly social mentor for the student.
Private Social Memory: {past_memories}"""
    
    if not client:
        return {"messages": [AIMessage(content="Social service unavailable.")]}
        
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=_iter_model_candidates()[0],
            contents=user_msg,
            config=types.GenerateContentConfig(system_instruction=prompt)
        )
        return {"messages": [AIMessage(content=response.text)]}
    except Exception:
        return {"messages": [AIMessage(content="Error generating social response.")]}

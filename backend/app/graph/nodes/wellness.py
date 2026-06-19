from app.graph.state import GraphState
from langchain_core.messages import AIMessage
from services.gemini_agent import _get_gemini_client, _iter_model_candidates
from langgraph.store.base import BaseStore
from langchain_core.runnables.config import RunnableConfig
import uuid

async def wellness_node(state: GraphState, config: RunnableConfig, store: BaseStore) -> dict:
    client = _get_gemini_client()
    user_msg = state["messages"][-1].content if state.get("messages") else ""
    user_id = state.get("user_id", "default")
    
    risk_level = "Standard"
    if any(w in user_msg.lower() for w in ["suicide", "harm", "die", "kill"]):
        risk_level = "Critical"
        
    if risk_level == "Critical":
        return {
            "messages": [AIMessage(content="I'm really sorry you're feeling this way. Please reach out to a professional immediately.")],
            "risk_level": risk_level
        }
        
    namespace = ("wellness", user_id)
    past_items = await store.asearch(namespace)
    past_memories = "\n".join([str(item.value) for item in past_items]) if past_items else "No past memories."
    
    await store.aput(namespace, str(uuid.uuid4()), {"query": user_msg})
        
    prompt = f"""You are a supportive wellness counselor.
Private Wellness Memory: {past_memories}"""
        
    if not client:
        return {"messages": [AIMessage(content="Wellness service unavailable.")]}
        
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=_iter_model_candidates()[0],
            contents=user_msg,
            config=types.GenerateContentConfig(system_instruction=prompt)
        )
        return {
            "messages": [AIMessage(content=response.text)],
            "risk_level": risk_level
        }
    except Exception:
        return {"messages": [AIMessage(content="Error generating wellness response.")]}

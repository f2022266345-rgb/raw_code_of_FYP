from app.graph.state import GraphState
from langchain_core.messages import AIMessage
from services.gemini_agent import _get_openai_client, _iter_model_candidates
from langgraph.store.base import BaseStore
from langchain_core.runnables.config import RunnableConfig
import uuid

async def social_node(state: GraphState, config: RunnableConfig, store: BaseStore) -> dict:
    client = _get_openai_client()
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
        response = client.chat.completions.create(
            model=_iter_model_candidates()[0],
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg}
            ]
        )
        return {"messages": [AIMessage(content=response.choices[0].message.content)]}
    except Exception:
        return {"messages": [AIMessage(content="Error generating social response.")]}

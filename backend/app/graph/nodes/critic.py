from app.graph.state import GraphState

async def critic_node(state: GraphState) -> dict:
    return {"risk_level": state.get("risk_level", "Standard")}

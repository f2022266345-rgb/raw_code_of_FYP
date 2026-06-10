from langgraph.graph import StateGraph, START, END
from app.graph.state import GraphState
from app.graph.nodes.gateway import gateway_node
from app.graph.nodes.coordinator import coordinator_node
from app.graph.nodes.academic import academic_node
from app.graph.nodes.social import social_node
from app.graph.nodes.wellness import wellness_node
from app.graph.nodes.critic import critic_node

def route_from_coordinator(state: GraphState) -> str:
    agent = state.get("active_agent", "academic")
    if agent == "wellness":
        return "wellness"
    elif agent == "social":
        return "social"
    return "academic"

def route_from_wellness(state: GraphState) -> str:
    if state.get("risk_level") == "Critical":
        return "escalation"
    return "critic"

def route_from_critic(state: GraphState) -> str:
    return END

async def escalation_node(state: GraphState) -> dict:
    from langchain_core.messages import AIMessage
    return {"messages": [AIMessage(content="ESCALATION: Human support has been notified.")]}

builder = StateGraph(GraphState)

builder.add_node("gateway", gateway_node)
builder.add_node("coordinator", coordinator_node)
builder.add_node("academic", academic_node)
builder.add_node("social", social_node)
builder.add_node("wellness", wellness_node)
builder.add_node("critic", critic_node)
builder.add_node("escalation", escalation_node)

builder.add_edge(START, "gateway")
builder.add_edge("gateway", "coordinator")

builder.add_conditional_edges(
    "coordinator",
    route_from_coordinator,
    {
        "academic": "academic",
        "social": "social",
        "wellness": "wellness"
    }
)

builder.add_edge("academic", "critic")
builder.add_edge("social", "critic")

builder.add_conditional_edges(
    "wellness",
    route_from_wellness,
    {
        "critic": "critic",
        "escalation": "escalation"
    }
)

builder.add_edge("escalation", END)
builder.add_conditional_edges(
    "critic",
    route_from_critic,
    {
        END: END,
        "academic": "academic",
        "social": "social",
        "wellness": "wellness"
    }
)

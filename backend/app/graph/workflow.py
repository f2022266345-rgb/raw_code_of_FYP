from langgraph.graph import StateGraph, START, END
from app.graph.state import GraphState
from app.graph.nodes.gateway import gateway_node
from app.graph.nodes.plan_nodes import (
    generate_academic_plan,
    generate_social_plan,
    generate_wellness_plan,
    synthesize_plan_node,
    human_support_node
)

def route_from_gateway(state: GraphState) -> list:
    profile = state.get("student_profile", {})
    if profile.get("requires_human_override", False):
        return ["human_support"]
    return ["academic_plan", "social_plan", "wellness_plan"]

builder = StateGraph(GraphState)

# 1. Add nodes
builder.add_node("gateway", gateway_node)
builder.add_node("academic_plan", generate_academic_plan)
builder.add_node("social_plan", generate_social_plan)
builder.add_node("wellness_plan", generate_wellness_plan)
builder.add_node("synthesize", synthesize_plan_node)
builder.add_node("human_support", human_support_node)

# 2. Add edges
builder.add_edge(START, "gateway")

# Fan-out / Circuit Breaker
builder.add_conditional_edges(
    "gateway",
    route_from_gateway,
    ["academic_plan", "social_plan", "wellness_plan", "human_support"]
)

# Fan-in
builder.add_edge("academic_plan", "synthesize")
builder.add_edge("social_plan", "synthesize")
builder.add_edge("wellness_plan", "synthesize")

builder.add_edge("synthesize", END)
builder.add_edge("human_support", END)

workflow = builder.compile()

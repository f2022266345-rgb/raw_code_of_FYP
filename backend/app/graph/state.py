from typing import TypedDict, Annotated, Sequence
from operator import add
from langchain_core.messages import BaseMessage

class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add]
    student_context: dict
    student_profile: dict
    active_agent: str
    risk_level: str
    user_id: str
    thread_id: str
    academic_plan: str
    social_plan: str
    wellness_plan: str
    final_plan: str

from typing import TypedDict, Annotated, Sequence
from operator import add
from langchain_core.messages import BaseMessage

class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add]
    student_context: dict
    active_agent: str
    risk_level: str
    user_id: str
    thread_id: str

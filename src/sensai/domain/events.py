from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

Now = Annotated[datetime, Field(default_factory=datetime.now)]


class Event(BaseModel):
    type: str
    timestamp: Now


class TextChunkEvent(Event):
    type: Literal["text_chunk"] = "text_chunk"
    content: str


class BudgetEvent(Event):
    type: Literal["budget"] = "budget"
    used: int
    max_tokens: int


class ToolCallEvent(Event):
    type: Literal["tool_call"] = "tool_call"
    tool_name: str
    arguments: dict[str, Any]

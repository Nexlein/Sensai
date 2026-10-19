from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from sensai.domain.models import GuardrailAction

Now = Annotated[datetime, Field(default_factory=datetime.now)]


class Event(BaseModel):
    type: str
    timestamp: Now


class AssistantStartEvent(Event):
    type: Literal["assistant_start"] = "assistant_start"


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


class ThoughtEvent(Event):
    """A reasoning step shown between tool calls, never part of the final answer."""

    type: Literal["thought"] = "thought"
    content: str
    source: Literal["native", "text"] = "text"


class StepEvent(Event):
    """A tool round is about to start: step `index` of at most `max_steps`."""

    type: Literal["step"] = "step"
    index: int
    max_steps: int


class MaxStepsEvent(Event):
    """The step cap was reached; the answer that follows is forced."""

    type: Literal["max_steps"] = "max_steps"
    max_steps: int


class GuardrailEvent(Event):
    type: Literal["guardrail"] = "guardrail"
    stage: Literal["input", "output", "tool"]
    action: GuardrailAction
    reason: str

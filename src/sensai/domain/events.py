from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

from sensai.domain.models import GuardrailAction


class Event(BaseModel):
    # Subclasses narrow `type` to a Literal; pyright flags narrowing a mutable field.
    type: str
    timestamp: datetime = Field(default_factory=datetime.now)


class AssistantStartEvent(Event):
    type: Literal["assistant_start"] = "assistant_start"  # pyright: ignore[reportIncompatibleVariableOverride]


class TextChunkEvent(Event):
    type: Literal["text_chunk"] = "text_chunk"  # pyright: ignore[reportIncompatibleVariableOverride]
    content: str


class BudgetEvent(Event):
    type: Literal["budget"] = "budget"  # pyright: ignore[reportIncompatibleVariableOverride]
    used: int
    max_tokens: int


class UsageEvent(Event):
    """Real counters the server reports at the end of one model call.

    Each field is None when the provider does not report it.
    """

    type: Literal["usage"] = "usage"  # pyright: ignore[reportIncompatibleVariableOverride]
    prompt_tokens: int | None = None
    reply_tokens: int | None = None
    prompt_seconds: float | None = None
    reply_seconds: float | None = None
    load_seconds: float | None = None
    total_seconds: float | None = None

    @computed_field
    @property
    def reply_rate(self) -> float | None:
        """Generation speed in tokens per second."""
        return _rate(self.reply_tokens, self.reply_seconds)

    @computed_field
    @property
    def prompt_rate(self) -> float | None:
        """Prompt reading (prefill) speed in tokens per second."""
        return _rate(self.prompt_tokens, self.prompt_seconds)

    @computed_field
    @property
    def first_token_seconds(self) -> float | None:
        """Model load plus prompt reading: the wait before the first reply token."""
        if self.prompt_seconds is None:
            return None
        return (self.load_seconds or 0.0) + self.prompt_seconds


def _rate(tokens: int | None, seconds: float | None) -> float | None:
    if tokens is None or not seconds:
        return None
    return tokens / seconds


class ToolCallEvent(Event):
    type: Literal["tool_call"] = "tool_call"  # pyright: ignore[reportIncompatibleVariableOverride]
    tool_name: str
    arguments: dict[str, Any]


class ThoughtEvent(Event):
    """A reasoning step shown between tool calls, never part of the final answer."""

    type: Literal["thought"] = "thought"  # pyright: ignore[reportIncompatibleVariableOverride]
    content: str
    source: Literal["native", "text"] = "text"


class StepEvent(Event):
    """A tool round is about to start: step `index` of at most `max_steps`."""

    type: Literal["step"] = "step"  # pyright: ignore[reportIncompatibleVariableOverride]
    index: int
    max_steps: int


class MaxStepsEvent(Event):
    """The step cap was reached; the answer that follows is forced."""

    type: Literal["max_steps"] = "max_steps"  # pyright: ignore[reportIncompatibleVariableOverride]
    max_steps: int


class GuardrailEvent(Event):
    type: Literal["guardrail"] = "guardrail"  # pyright: ignore[reportIncompatibleVariableOverride]
    stage: Literal["input", "output", "tool"]
    action: GuardrailAction
    reason: str

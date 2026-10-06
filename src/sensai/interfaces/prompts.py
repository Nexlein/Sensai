import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from sensai.domain.models import ToolCall

T = TypeVar("T")

DETAIL_MAX_LENGTH = 80


@dataclass(frozen=True)
class Option(Generic[T]):
    label: str
    value: T


@dataclass(frozen=True)
class Question(Generic[T]):
    title: str
    options: tuple[Option[T], ...]
    cancel_value: T
    details: tuple[tuple[str, str], ...] = ()

    def resolve(self, answer: str) -> T:
        text = answer.strip().lower()
        if not text:
            return self.options[0].value
        if text.isdigit() and 1 <= int(text) <= len(self.options):
            return self.options[int(text) - 1].value
        for option in self.options:
            label = option.label.lower()
            if text in {label, label[0]}:
                return option.value
        return self.cancel_value


AskFn = Callable[[Question[T]], Awaitable[T]]


def _detail_value(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    if len(text) > DETAIL_MAX_LENGTH:
        return text[: DETAIL_MAX_LENGTH - 1] + "…"
    return text


def tool_confirmation(tc: ToolCall) -> Question[bool]:
    return Question(
        title=f"Allow {tc.name}?",
        options=(Option("Yes", True), Option("No", False)),
        cancel_value=False,
        details=tuple((key, _detail_value(v)) for key, v in tc.arguments.items()),
    )


def tool_decision(tc: ToolCall, approved: bool) -> str:
    return f"✓ allowed {tc.name}" if approved else f"✗ declined {tc.name}"

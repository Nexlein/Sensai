import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from sensai.domain.models import ToolCall

T = TypeVar("T")

DETAIL_MAX_LENGTH = 80


@dataclass(frozen=True)
class Option(Generic[T]):
    label: str
    value: T
    hint: str = ""

    @property
    def text(self) -> str:
        return f"{self.label} ({self.hint})" if self.hint else self.label


@dataclass(frozen=True)
class Question(Generic[T]):
    title: str
    options: tuple[Option[T], ...]
    cancel_value: T
    details: tuple[tuple[str, str], ...] = ()
    initial: int = 0

    def resolve(self, answer: str) -> T:
        text = answer.strip().lower()
        if not text:
            return self.options[self.initial].value
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


def choice_question(
    title: str,
    labels: Sequence[str],
    current: str | None = None,
    notes: Mapping[str, str] | None = None,
) -> Question[str | None]:
    """A pick-one question over plain labels; cancelling answers None.

    The `current` label is marked and preselected; `notes` adds text after a label.
    """
    notes = notes or {}
    return Question(
        title=title,
        options=tuple(
            Option(
                label.capitalize(),
                label,
                ", ".join(
                    part
                    for part in (notes.get(label, ""), "current" * (label == current))
                    if part
                ),
            )
            for label in labels
        ),
        cancel_value=None,
        initial=labels.index(current) if current in labels else 0,
    )


def tool_confirmation(tc: ToolCall) -> Question[bool]:
    arguments = list(tc.arguments.items())
    if tc.preview is not None:
        # The diff already shows the new content or code above the prompt.
        arguments = [(key, v) for key, v in arguments if key not in ("content", "code")]
    return Question(
        title=f"Allow {tc.name}?",
        options=(Option("Yes", True), Option("No", False)),
        cancel_value=False,
        details=tuple((key, _detail_value(v)) for key, v in arguments),
    )


def tool_decision(tc: ToolCall, approved: bool) -> str:
    return f"✓ allowed {tc.name}" if approved else f"✗ declined {tc.name}"

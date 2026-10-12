import asyncio
from typing import ClassVar, Generic, TypeVar

from rich.text import Text
from textual import events
from textual.binding import Binding, BindingType
from textual.reactive import reactive
from textual.widget import Widget

from sensai.interfaces.prompts import Question

T = TypeVar("T")

HINT = "↑↓ select · enter confirm · esc cancel"


class QuestionPrompt(Widget, Generic[T], can_focus=True):
    DEFAULT_CSS = """
    QuestionPrompt {
        dock: bottom;
        height: auto;
        margin: 0 1;
        padding: 0 1;
        border: round $accent;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", show=False),
        Binding("down", "move(1)", show=False),
        Binding("enter", "choose", show=False),
        Binding("escape", "cancel", show=False),
    ]

    index: reactive[int] = reactive(0)

    def __init__(self, question: Question[T]) -> None:
        super().__init__()
        self.question = question
        self.answer: asyncio.Future[T] = asyncio.get_running_loop().create_future()

    def render(self) -> Text:
        text = Text()
        text.append(f"{self.question.title}\n", style="bold")
        width = max((len(key) for key, _ in self.question.details), default=0)
        for key, value in self.question.details:
            text.append(f"  {key.ljust(width)}  ", style="dim")
            text.append(f"{value}\n")
        text.append("\n")
        for position, option in enumerate(self.question.options):
            line = f"{position + 1}. {option.label}\n"
            if position == self.index:
                text.append(f"❯ {line}", style="bold #bb9af7")
            else:
                text.append(f"  {line}")
        text.append(f"\n{HINT}", style="dim italic")
        return text

    def _resolve(self, value: T) -> None:
        if not self.answer.done():
            self.answer.set_result(value)

    def action_move(self, step: int) -> None:
        self.index = (self.index + step) % len(self.question.options)

    def action_choose(self) -> None:
        self._resolve(self.question.options[self.index].value)

    def action_cancel(self) -> None:
        self._resolve(self.question.cancel_value)

    def on_key(self, event: events.Key) -> None:
        if event.character and event.character.isdigit():
            position = int(event.character) - 1
            if 0 <= position < len(self.question.options):
                event.stop()
                self._resolve(self.question.options[position].value)

from typing import TypeVar

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import FormattedTextControl, HSplit, Layout, Window
from prompt_toolkit.styles import Style

from sensai.interfaces.prompts import Question

T = TypeVar("T")

HINT = "↑↓ select · enter confirm · esc cancel"

STYLE = Style.from_dict(
    {
        "title": "bold",
        "detail-key": "#888888",
        "selected": "bold #bb9af7",
        "hint": "#888888 italic",
    }
)


def question_fragments(question: Question[T], index: int) -> StyleAndTextTuples:
    fragments: StyleAndTextTuples = [("class:title", f"  {question.title}\n")]
    width = max((len(key) for key, _ in question.details), default=0)
    for key, value in question.details:
        fragments.append(("class:detail-key", f"    {key.ljust(width)}  "))
        fragments.append(("", f"{value}\n"))
    fragments.append(("", "\n"))
    for position, option in enumerate(question.options):
        line = f"{position + 1}. {option.label}\n"
        if position == index:
            fragments.append(("class:selected", f"  ❯ {line}"))
        else:
            fragments.append(("", f"    {line}"))
    fragments.append(("class:hint", f"\n  {HINT}"))
    return fragments


def build_select(question: Question[T]) -> Application[T]:
    index = 0
    bindings = KeyBindings()

    @bindings.add("up")
    def _up(event: KeyPressEvent) -> None:
        nonlocal index
        index = (index - 1) % len(question.options)

    @bindings.add("down")
    def _down(event: KeyPressEvent) -> None:
        nonlocal index
        index = (index + 1) % len(question.options)

    @bindings.add("enter")
    def _enter(event: KeyPressEvent) -> None:
        event.app.exit(result=question.options[index].value)

    @bindings.add("escape", eager=True)
    @bindings.add("c-c")
    @bindings.add("c-d")
    def _cancel(event: KeyPressEvent) -> None:
        event.app.exit(result=question.cancel_value)

    for position, option in enumerate(question.options[:9]):

        @bindings.add(str(position + 1))
        def _pick(event: KeyPressEvent, value: T = option.value) -> None:
            event.app.exit(result=value)

    control = FormattedTextControl(lambda: question_fragments(question, index))
    return Application(
        layout=Layout(HSplit([Window(control, dont_extend_height=True)])),
        key_bindings=bindings,
        style=STYLE,
        full_screen=False,
        erase_when_done=True,
    )


async def select(question: Question[T]) -> T:
    return await build_select(question).run_async()

from collections.abc import AsyncIterator, Awaitable, Callable

from sensai.core.engine import ChatEngine
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event

ReadInputFn = Callable[[], str]
RenderFn = Callable[[AsyncIterator[Event]], Awaitable[None]]
ErrorFn = Callable[[Exception], None]


def is_exit_command(text: str) -> bool:
    return text.strip().lower() == "exit"


async def run_repl(
    engine: ChatEngine,
    *,
    read_input: ReadInputFn,
    render: RenderFn,
    on_error: ErrorFn,
) -> None:
    while True:
        try:
            text = read_input()
        except (EOFError, KeyboardInterrupt):
            break

        if is_exit_command(text):
            break

        try:
            await render(engine.send(text))
        except (EmptyInputError, ProviderError) as exc:
            on_error(exc)

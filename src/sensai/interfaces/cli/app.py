"""Terminal frontend for a shared Sensai session."""

import asyncio
import signal
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence

from rich.console import Console

from sensai.core.commands import CommandContext, CommandResult
from sensai.core.input import process_input
from sensai.core.tool_runner import ConfirmTool
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event
from sensai.interfaces.cli.renderer import CliRenderer, render_history
from sensai.interfaces.notices import error_text
from sensai.interfaces.prompts import choice_question


async def run_cli(context: CommandContext, console: Console) -> None:
    console.clear()
    show_thoughts = context.config.reasoning.show_thoughts
    render_history(console, context.engine.conversation, show_thoughts)

    def read_input() -> str:
        return console.input("[bold blue]you:[/] ")

    renderer = CliRenderer(console, show_thoughts)

    async def choose(
        title: str,
        labels: Sequence[str],
        current: str | None,
        notes: Mapping[str, str],
    ) -> str | None:
        return await renderer.ask(choice_question(title, labels, current, notes))

    context.choose = choose

    async def render(events: AsyncIterator[Event]) -> None:
        console.print()
        await renderer.render(events)
        console.print()

    def on_error(exc: Exception) -> None:
        console.print(f"[bold red]✗ {error_text(exc)}[/]")

    await run_repl(
        context,
        read_input=read_input,
        render=render,
        on_error=on_error,
        confirm_tool=renderer.confirm_tool,
        on_stop=lambda: console.print("[yellow]Stopped.[/]"),
    )


async def _stoppable(turn: Awaitable[CommandResult]) -> CommandResult | None:
    """Run one turn so that Ctrl+C stops it, not the whole app; None if stopped."""
    loop = asyncio.get_running_loop()
    task = asyncio.ensure_future(turn)
    try:
        loop.add_signal_handler(signal.SIGINT, task.cancel)
    except (NotImplementedError, RuntimeError, ValueError):
        pass  # no signal support here: Ctrl+C keeps its default meaning
    try:
        return await task
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise  # the whole app is being cancelled, not just this turn
        return None
    finally:
        try:
            loop.remove_signal_handler(signal.SIGINT)
        except (NotImplementedError, RuntimeError, ValueError):
            pass


ReadInputFn = Callable[[], str]
RenderFn = Callable[[AsyncIterator[Event]], Awaitable[None]]
ErrorFn = Callable[[Exception], None]


async def run_repl(
    context: CommandContext,
    *,
    read_input: ReadInputFn,
    render: RenderFn,
    on_error: ErrorFn,
    confirm_tool: ConfirmTool | None = None,
    on_stop: Callable[[], None] = lambda: None,
) -> None:
    while True:
        try:
            text = read_input()
        except (EOFError, KeyboardInterrupt):
            break

        try:
            result = await _stoppable(
                process_input(context, text, render, confirm_tool=confirm_tool)
            )
        except (EmptyInputError, ProviderError) as exc:
            on_error(exc)
            continue
        if result is None:
            on_stop()
            continue

        if result.message:
            Console().print(result.message)
        if result.should_exit:
            break

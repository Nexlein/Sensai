"""Terminal frontend for a shared Sensai session."""

from collections.abc import AsyncIterator, Awaitable, Callable

from rich.console import Console

from sensai.core.commands import CommandContext
from sensai.core.engine import ConfirmTool
from sensai.core.input import process_input
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event
from sensai.interfaces.cli.renderer import CliRenderer, error_text, render_history


async def run_cli(context: CommandContext, console: Console) -> None:
    console.clear()
    render_history(console, context.engine.conversation)

    def read_input() -> str:
        return console.input("[bold blue]you:[/] ")

    renderer = CliRenderer(console)

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
    )


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
) -> None:
    while True:
        try:
            text = read_input()
        except (EOFError, KeyboardInterrupt):
            break

        try:
            result = await process_input(
                context, text, render, confirm_tool=confirm_tool
            )
        except (EmptyInputError, ProviderError) as exc:
            on_error(exc)
            continue

        if result.message:
            Console().print(result.message)
        if result.should_exit:
            break

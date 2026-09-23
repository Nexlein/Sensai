import asyncio
import sys
from collections.abc import AsyncIterator

from rich.console import Console

from sensai.core.commands import run_repl
from sensai.core.config import ConfigError, resolve_config
from sensai.core.engine import ChatEngine
from sensai.domain.errors import ProviderError
from sensai.domain.events import Event
from sensai.domain.models import Conversation
from sensai.interfaces.cli.renderer import error_text, render_stream
from sensai.providers import get_provider


async def _run(argv: list[str]) -> int:
    console = Console()

    try:
        config = resolve_config(argv)
    except ConfigError as exc:
        console.print(f"[bold red]✗ {exc}[/]")
        return 1

    try:
        provider = get_provider(
            config.provider, base_url=config.base_url, model=config.model
        )
    except ProviderError as exc:
        console.print(f"[bold red]✗ {exc}[/]")
        return 1

    engine = ChatEngine(provider, Conversation())

    console.clear()

    def read_input() -> str:
        return console.input("[bold blue]you:[/] ")

    async def render(events: AsyncIterator[Event]) -> None:
        console.print()
        await render_stream(console, events)

    def on_error(exc: Exception) -> None:
        console.print(f"[bold red]✗ {error_text(exc)}[/]")

    await run_repl(engine, read_input=read_input, render=render, on_error=on_error)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run(sys.argv[1:])))

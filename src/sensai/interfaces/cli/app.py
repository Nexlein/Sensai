import asyncio
import sys
from collections.abc import AsyncIterator

from rich.console import Console

from sensai.core.commands import run_repl
from sensai.core.config import ConfigError, resolve_config, resolve_session
from sensai.core.engine import ChatEngine
from sensai.domain.errors import ProviderError
from sensai.domain.events import Event
from sensai.domain.models import Conversation
from sensai.interfaces.cli.renderer import error_text, render_history, render_stream
from sensai.memory.session import SqliteMemoryStore
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

    store = SqliteMemoryStore()
    session_name = resolve_session(argv)
    conversation = None
    if session_name is not None:
        conversation = await store.load(session_name)
    if conversation is None:
        conversation = Conversation(id=session_name) if session_name else Conversation()

    engine = ChatEngine(provider, conversation)

    console.clear()
    render_history(console, conversation)

    def read_input() -> str:
        return console.input("[bold blue]you:[/] ")

    async def render(events: AsyncIterator[Event]) -> None:
        console.print()
        await render_stream(console, events)
        await store.save(engine.conversation)

    def on_error(exc: Exception) -> None:
        console.print(f"[bold red]✗ {error_text(exc)}[/]")

    await run_repl(engine, read_input=read_input, render=render, on_error=on_error)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run(sys.argv[1:])))

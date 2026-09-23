import asyncio
import sys
from collections.abc import AsyncIterator

from rich.console import Console

from sensai.core.commands import CommandContext, run_repl
from sensai.core.config import (
    ConfigError,
    resolve_config,
    resolve_config_path,
    resolve_session,
)
from sensai.core.engine import ChatEngine
from sensai.domain.errors import ProviderError
from sensai.domain.events import Event
from sensai.domain.models import Conversation
from sensai.interfaces.cli.renderer import error_text, render_history, render_stream
from sensai.memory.session import SqliteMemoryStore
from sensai.providers import get_provider
from sensai.tools.fs import ListDirTool, ReadFileTool
from sensai.tools.registry import ToolRegistry


def _build_tool_registry(allowed_root: str | None) -> ToolRegistry:
    registry = ToolRegistry()
    if allowed_root is not None:
        registry.register(ReadFileTool(allowed_root))
        registry.register(ListDirTool(allowed_root))
    return registry


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

    tool_registry = _build_tool_registry(config.tools.fs_allowed_root)
    engine = ChatEngine(provider, conversation, tool_registry)

    context = CommandContext(
        config=config,
        engine=engine,
        output=console.print,
        provider_factory=get_provider,
        tool_registry=tool_registry,
        tool_registry_factory=_build_tool_registry,
        memory_store=store,
        config_path=resolve_config_path(argv),
    )

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

    await run_repl(context, read_input=read_input, render=render, on_error=on_error)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run(sys.argv[1:])))

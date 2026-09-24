import asyncio
import sys
from collections.abc import AsyncIterator, Awaitable, Callable

from rich.console import Console

from sensai.core.commands import (
    CommandContext,
    dispatch_command,
    parse_commands,
)
from sensai.core.config import DEFAULT_CONFIG_PATH, AppConfig, ConfigError, load_config
from sensai.core.engine import ChatEngine
from sensai.domain.errors import EmptyInputError, ProviderError
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


import argparse
from pathlib import Path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sensai")
    subparsers = parser.add_subparsers(dest="command")

    chat = subparsers.add_parser("chat", help="Start an interactive chat session")
    chat.add_argument("--model", default=None, help="Model name to use")
    chat.add_argument("--provider", default=None, help="Provider to use")
    chat.add_argument("--base-url", default=None, help="Base URL of the provider")
    chat.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to the config file",
    )
    chat.add_argument(
        "--session",
        default=None,
        help="Name of the session to resume or create",
    )
    return parser


def resolve_config(argv: list[str]) -> AppConfig:
    """Parse CLI args and resolve the effective AppConfig from them."""
    args = build_arg_parser().parse_args(argv)
    return load_config(
        getattr(args, "config", DEFAULT_CONFIG_PATH),
        cli_provider=getattr(args, "provider", None),
        cli_model=getattr(args, "model", None),
        cli_base_url=getattr(args, "base_url", None),
    )


def resolve_session(argv: list[str]) -> str | None:
    """Parse CLI args and return the --session name, if any."""
    args = build_arg_parser().parse_args(argv)
    return getattr(args, "session", None)


def resolve_config_path(argv: list[str]) -> Path:
    """Parse CLI args and return the selected config file path."""
    args = build_arg_parser().parse_args(argv)
    return Path(getattr(args, "config", DEFAULT_CONFIG_PATH))


ReadInputFn = Callable[[], str]
RenderFn = Callable[[AsyncIterator[Event]], Awaitable[None]]
ErrorFn = Callable[[Exception], None]


async def run_repl(
    context: CommandContext,
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

        command = parse_commands(text)

        if command is not None:
            result = await dispatch_command(command, context)

            if result.message:
                Console().print(result.message)
            if result.should_exit:
                break
            continue
        try:
            await render(context.engine.send(text))
        except (EmptyInputError, ProviderError) as exc:
            on_error(exc)

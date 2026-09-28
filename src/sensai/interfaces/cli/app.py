import argparse
import asyncio
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from rich.console import Console

from sensai.core.bootstrap import BootstrapError, build_session
from sensai.core.commands import CommandContext, dispatch_command, parse_commands
from sensai.core.config import DEFAULT_CONFIG_PATH, ConfigError
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event
from sensai.interfaces.cli.renderer import error_text, render_history, render_stream


async def _run(argv: list[str]) -> int:
    console = Console()
    args = build_arg_parser().parse_args(argv)

    try:
        context = await build_session(
            config_path=getattr(args, "config", DEFAULT_CONFIG_PATH),
            provider_name=getattr(args, "provider", None),
            model=getattr(args, "model", None),
            base_url=getattr(args, "base_url", None),
            session_name=getattr(args, "session", None),
            rag_dir=getattr(args, "rag_dir", None),
            rag_db=getattr(args, "rag_db", "rag.db"),
            rag_model=getattr(args, "rag_model", "nomic-embed-text"),
        )
    except (BootstrapError, ConfigError, ProviderError) as exc:
        console.print(f"[bold red]✗ {exc}[/]")
        return 1

    console.clear()
    render_history(console, context.engine.conversation)

    def read_input() -> str:
        return console.input("[bold blue]you:[/] ")

    async def render(events: AsyncIterator[Event]) -> None:
        console.print()
        await render_stream(console, events)
        await context.memory_store.save(context.engine.conversation)

    def on_error(exc: Exception) -> None:
        console.print(f"[bold red]✗ {error_text(exc)}[/]")

    await run_repl(context, read_input=read_input, render=render, on_error=on_error)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run(sys.argv[1:])))


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
        "--rag-dir", default=None, help="Directory of .txt and .md files to index"
    )
    chat.add_argument("--rag-db", default="rag.db", help="Path to the local RAG index")
    chat.add_argument(
        "--rag-model", default="nomic-embed-text", help="Ollama embedding model"
    )
    chat.add_argument(
        "--session",
        default=None,
        help="Name of the session to resume or create",
    )
    return parser


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

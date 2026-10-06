"""Sensai command-line entry point and interface dispatcher."""

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console

from sensai.core.bootstrap import BootstrapError, build_session
from sensai.core.config import DEFAULT_CONFIG_PATH, ConfigError
from sensai.domain.errors import ProviderError
from sensai.interfaces.cli.app import run_cli
from sensai.interfaces.tui.app import run_tui


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sensai")
    subparsers = parser.add_subparsers(dest="command")

    chat = subparsers.add_parser("chat", help="Start an interactive chat session")
    chat.add_argument(
        "--ui", choices=("cli", "tui", "web"), default=None, help="Interface to use"
    )
    chat.add_argument("--model", default=None, help="Model name to use")
    chat.add_argument("--provider", default=None, help="Provider to use")
    chat.add_argument("--base-url", default=None, help="Base URL of the provider")
    chat.add_argument(
        "--config", default=str(DEFAULT_CONFIG_PATH), help="Path to the config file"
    )
    chat.add_argument(
        "--rag-dir", default=None, help="Directory of .txt and .md files to index"
    )
    chat.add_argument("--rag-db", default="rag.db", help="Path to the local RAG index")
    chat.add_argument(
        "--rag-model", default="nomic-embed-text", help="Ollama embedding model"
    )
    chat.add_argument(
        "--session", default=None, help="Name of the session to resume or create"
    )
    return parser


async def dispatch(argv: list[str]) -> int:
    """Build one session, then run the selected interface."""
    console = Console()
    args = build_arg_parser().parse_args(argv)

    try:
        context = await build_session(
            config_path=getattr(args, "config", DEFAULT_CONFIG_PATH),
            interface=getattr(args, "ui", None),
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

    if context.config.interface == "cli":
        await run_cli(context, console)
        return 0
    if context.config.interface == "tui":
        await run_tui(context)
        return 0

    console.print("[bold red]✗ Web interface is not implemented yet.[/]")
    return 1


def main() -> None:
    raise SystemExit(asyncio.run(dispatch(sys.argv[1:])))


def resolve_session(argv: list[str]) -> str | None:
    args = build_arg_parser().parse_args(argv)
    return getattr(args, "session", None)


def resolve_config_path(argv: list[str]) -> Path:
    args = build_arg_parser().parse_args(argv)
    return Path(getattr(args, "config", DEFAULT_CONFIG_PATH))

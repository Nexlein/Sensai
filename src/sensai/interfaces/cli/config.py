"""`sensai config ...`: read and edit the config file from the shell."""

import argparse
from pathlib import Path

from rich.console import Console

from sensai.core.config import ConfigError, load_config, to_file_value
from sensai.core.config_file import write_text
from sensai.core.settings import (
    assign,
    format_keys,
    format_settings,
    format_value,
    get_value,
    save_setting,
    sources,
    template,
    validated,
)

ACTIONS = ("show", "get", "set", "reset", "keys", "init", "path")


def add_config_parser(
    subparsers: argparse._SubParsersAction, default_path: str
) -> None:
    """Register `sensai config` and its actions."""
    parser = subparsers.add_parser(
        "config",
        help="Show or edit sensai.toml",
        description="Show or edit the config file. Values are TOML literals: "
        'true, 0.2, 8192, "text"; none resets a value.',
    )
    parser.add_argument("action", choices=ACTIONS, nargs="?", default="show")
    parser.add_argument(
        "key", nargs="?", default=None, help="Dotted key, e.g. options.temperature"
    )
    parser.add_argument("value", nargs="*", help="New value (set only)")
    parser.add_argument(
        "--config", default=default_path, help="Path to the config file"
    )
    parser.add_argument("--force", action="store_true", help="init: overwrite the file")


def _write(console: Console, text: str) -> None:
    console.print(text, markup=False, highlight=False)


def _change(path: Path, key: str, raw: str | None) -> str:
    config = load_config(path)
    assign(config, key, validated(config, key, raw))
    save_setting(config, key, path, reset=raw is None)
    value = to_file_value(key, get_value(config, key))
    return f"{key} = {format_value(key, value)} (saved to {path})"


def _run(args: argparse.Namespace, console: Console) -> str:
    path = Path(args.config)
    action, key = args.action, args.key
    if action == "path":
        return str(path.resolve())
    if action == "keys":
        return format_keys(key)
    if action == "init":
        if path.exists() and not args.force:
            raise ConfigError(f"{path} already exists (use --force to overwrite it)")
        write_text(path, template())
        return f"Wrote {path} with every setting documented at its default."
    if action in {"set", "reset", "get"} and key is None:
        raise ConfigError(
            f"Usage: sensai config {action} <key>"
            + (" <value>" if action == "set" else "")
        )
    if action == "set":
        if not args.value:
            raise ConfigError("Usage: sensai config set <key> <value>")
        return _change(path, key, " ".join(args.value))
    if action == "reset":
        return _change(path, key, None)
    config = load_config(path)
    found = sources(config, path)
    if action == "get" and "." in key and key in found:
        return (
            f"{key} = {format_value(key, to_file_value(key, get_value(config, key)))}"
        )
    header = f"Config file: {path}" + ("" if path.exists() else " (missing: defaults)")
    return f"{header}\n\n{format_settings(config, found, key)}"


def run_config_command(args: argparse.Namespace, console: Console | None = None) -> int:
    """Run one `sensai config` action; 1 with a one-line reason on failure."""
    console = console or Console()
    try:
        _write(console, _run(args, console))
    except ConfigError as exc:
        console.print(f"[bold red]✗[/] {exc}", highlight=False)
        return 1
    return 0

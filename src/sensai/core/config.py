import argparse
from pathlib import Path
from typing import Any

import tomllib
from pydantic import BaseModel, ValidationError

DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "llama3.2"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_CONFIG_PATH = Path("sensai.toml")


class ConfigError(Exception):
    """Raised when a config file exists but cannot be parsed or validated."""


class ToolsConfig(BaseModel):
    fs_allowed_root: str | None = None


class AppConfig(BaseModel):
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    tools: ToolsConfig = ToolsConfig()


def _read_config_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Malformed config file {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read config file {path}: {exc}") from exc


def load_config(
    config_path: Path | str | None = DEFAULT_CONFIG_PATH,
    *,
    cli_provider: str | None = None,
    cli_model: str | None = None,
    cli_base_url: str | None = None,
) -> AppConfig:
    """Resolve config with precedence: CLI arg > config file > built-in default.

    A missing config file silently falls back to defaults. A config file that
    exists but is malformed or fails validation raises ConfigError.
    """
    file_data: dict[str, Any] = {}
    if config_path is not None:
        path = Path(config_path)
        if path.exists():
            file_data = _read_config_file(path)

    merged = {**file_data}
    if cli_provider is not None:
        merged["provider"] = cli_provider
    if cli_model is not None:
        merged["model"] = cli_model
    if cli_base_url is not None:
        merged["base_url"] = cli_base_url

    try:
        return AppConfig(**merged)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config values: {exc}") from exc


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

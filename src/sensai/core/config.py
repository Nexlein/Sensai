import json
from pathlib import Path
from typing import Any, Literal

import tomllib
from pydantic import BaseModel, ValidationError

DEFAULT_INTERFACE = "cli"
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "llama3.2"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_CONFIG_PATH = Path("sensai.toml")


class ConfigError(Exception):
    """Raised when a config file exists but cannot be parsed or validated."""


class ToolsConfig(BaseModel):
    fs_allowed_root: str | None = None


class GuardrailsConfig(BaseModel):
    """Privacy/content guardrails (EV2). Opt-in: off unless `enabled` is set."""

    enabled: bool = False
    injection: Literal["block", "flag"] = "block"
    pii: Literal["redact", "block"] = "redact"


class AppConfig(BaseModel):
    interface: Literal["cli", "tui", "web"] = DEFAULT_INTERFACE
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    tools: ToolsConfig = ToolsConfig()
    guardrails: GuardrailsConfig = GuardrailsConfig()


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
    interface: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
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
    if interface is not None:
        merged["interface"] = interface
    if provider is not None:
        merged["provider"] = provider
    if model is not None:
        merged["model"] = model
    if base_url is not None:
        merged["base_url"] = base_url

    try:
        return AppConfig(**merged)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config values: {exc}") from exc


def save_config(
    config: AppConfig,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> None:
    path = Path(config_path)
    lines = [
        f"interface = {json.dumps(config.interface, ensure_ascii=False)}",
        f"provider = {json.dumps(config.provider, ensure_ascii=False)}",
        f"model = {json.dumps(config.model, ensure_ascii=False)}",
        f"base_url = {json.dumps(config.base_url, ensure_ascii=False)}",
    ]

    if config.tools.fs_allowed_root is not None:
        lines.extend(
            [
                "",
                "[tools]",
                "fs_allowed_root = "
                + json.dumps(config.tools.fs_allowed_root, ensure_ascii=False),
            ]
        )

    if config.guardrails != GuardrailsConfig():
        lines.extend(
            [
                "",
                "[guardrails]",
                f"enabled = {json.dumps(config.guardrails.enabled)}",
                f"injection = {json.dumps(config.guardrails.injection)}",
                f"pii = {json.dumps(config.guardrails.pii)}",
            ]
        )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not write config file {path}: {exc}") from exc

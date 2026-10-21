"""Sensai settings: the schema, loading with precedence, and saving.

Precedence is CLI flag > config file (`sensai.toml`) > built-in default. Every field
carries a description, which `/config keys`, `sensai config init` and the docs use.
A field marked `restart` only takes effect when Sensai starts again.
"""

import re
from pathlib import Path
from typing import Any, Literal

import tomllib
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from sensai.core.budget import BudgetConfig
from sensai.core.config_file import ConfigError, flatten, read_document, update_file
from sensai.domain.models import ModelOptions

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_EFFORT",
    "DEFAULT_INTERFACE",
    "DEFAULT_MODEL",
    "DEFAULT_NUM_CTX",
    "DEFAULT_PROVIDER",
    "AppConfig",
    "ConfigError",
    "check_context_fits",
    "load_config",
    "save_config",
]

DEFAULT_INTERFACE = "cli"
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "qwen3.5:4b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_CONFIG_PATH = Path("sensai.toml")
DEFAULT_EFFORT = "low"
DEFAULT_NUM_CTX = 8192
RESTART = {"restart": True}
_SERVER_NAME = re.compile(r"[A-Za-z0-9_-]+")


class ToolsConfig(BaseModel):
    """Built-in tools the model may call."""

    fs_allowed_root: str | None = Field(
        default=".",
        description="Root of read_file/list_dir/write_file, relative to the launch "
        "directory; false turns the file tools off",
    )
    web_search: bool = Field(
        default=True, description="Register web_search (local SearXNG on :8888)"
    )
    sandbox: bool = Field(
        default=True, description="Register run_python (throwaway Docker container)"
    )

    @field_validator("fs_allowed_root", mode="before")
    @classmethod
    def _false_disables_fs_tools(cls, value: Any) -> Any:
        """TOML has no null, so `fs_allowed_root = false` turns the fs tools off."""
        return None if value is False else value


class GuardrailsConfig(BaseModel):
    """Privacy/content guardrails (EV2). On by default; `enabled = false` opts out."""

    enabled: bool = Field(
        default=True, description="Filter input, replies and tool results"
    )
    injection: Literal["block", "flag"] = Field(
        default="block", description="On a prompt-injection match: block or warn only"
    )
    pii: Literal["redact", "block"] = Field(
        default="redact", description="On personal data: mask it or refuse the text"
    )


class EvalConfig(BaseModel):
    """Opt-in logs: replies (EV1, graded with `python -m sensai.eval.judge`) and the
    full prompt of every model call."""

    log_replies: bool = Field(
        default=False, description="Append each final reply to replies_path"
    )
    replies_path: str = Field(
        default="logs/replies.jsonl", description="JSONL file of replies"
    )
    log_prompts: bool = Field(
        default=False,
        description="Append every prompt sent to the model to prompts_path",
    )
    prompts_path: str = Field(
        default="logs/prompts.jsonl", description="JSONL file of prompts"
    )


class McpServerConfig(BaseModel):
    """One MCP server Sensai launches as a child process (stdio transport)."""

    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    timeout: float = 30.0

    @field_validator("command")
    @classmethod
    def _command_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("command must not be empty")
        return value

    @field_validator("timeout")
    @classmethod
    def _timeout_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout must be positive")
        return value


class McpConfig(BaseModel):
    """`[mcp.servers.<name>]` tables. The name prefixes the server's tool names."""

    servers: dict[str, McpServerConfig] = Field(
        default={},
        description="MCP servers started at launch; edit them in the file",
        json_schema_extra=RESTART,
    )

    @field_validator("servers")
    @classmethod
    def _names_are_identifiers(
        cls, servers: dict[str, McpServerConfig]
    ) -> dict[str, McpServerConfig]:
        """Tool names reach the model as `<name>__<tool>`, so keep them function-safe."""
        for name in servers:
            if not _SERVER_NAME.fullmatch(name):
                raise ValueError(
                    f"invalid MCP server name {name!r}: use letters, digits, '-', '_'"
                )
        return servers


class MemoryConfig(BaseModel):
    """Structured long-term memory (M3). On by default; `enabled = false` opts out."""

    enabled: bool = Field(
        default=True,
        description="Structured memory tools and /memory",
        json_schema_extra=RESTART,
    )
    auto_inject: bool = Field(
        default=True, description="Put the remembered facts in every prompt"
    )


class PersonaConfig(BaseModel):
    """Domain system prompt placed first in every call. Off by default."""

    enabled: bool = Field(
        default=False, description="Lead every prompt with the persona"
    )
    name: str = Field(default="Sensai", description="Name shown by /persona")
    instruction: str | None = Field(
        default=None, description="Persona text (or use file, not both)"
    )
    file: str | None = Field(
        default=None,
        description="Text file holding the persona, relative to the launch directory",
    )

    @model_validator(mode="after")
    def _one_source(self) -> "PersonaConfig":
        if self.instruction is not None and self.file is not None:
            raise ValueError("set either instruction or file, not both")
        if self.enabled and self.instruction is None and self.file is None:
            raise ValueError("enabled persona needs an instruction or a file")
        return self


class RagConfig(BaseModel):
    """Local document retrieval. Off by default; `--rag-dir` also turns it on."""

    enabled: bool = Field(
        default=False,
        description="Index dir at launch and retrieve per question",
        json_schema_extra=RESTART,
    )
    dir: str | None = Field(
        default=None,
        description="Directory of .md/.txt files",
        json_schema_extra=RESTART,
    )
    model: str = Field(
        default="nomic-embed-text",
        description="Ollama embedding model",
        json_schema_extra=RESTART,
    )
    db: str = Field(
        default="rag.db", description="SQLite index file", json_schema_extra=RESTART
    )
    top_k: int = Field(
        default=5,
        ge=1,
        description="Chunks added to each prompt",
        json_schema_extra=RESTART,
    )
    chunk_size: int = Field(
        default=500, gt=0, description="Characters per chunk", json_schema_extra=RESTART
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        description="Characters shared by consecutive chunks (< chunk_size)",
        json_schema_extra=RESTART,
    )

    @model_validator(mode="after")
    def _coherent(self) -> "RagConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.enabled and not self.dir:
            raise ValueError("enabled RAG needs a dir")
        return self


class ReasoningConfig(BaseModel):
    """Visible reasoning loop: thoughts and steps between tool calls."""

    enabled: bool = Field(
        default=True, description="Step and thought events, think effort"
    )
    show_thoughts: bool = Field(
        default=False,
        description="Show thoughts and steps (answers then appear per round)",
        json_schema_extra=RESTART,
    )
    max_steps: int = Field(
        default=5, ge=1, description="Tool rounds before a forced tool-free answer"
    )
    think: bool | Literal["low", "medium", "high"] | None = Field(
        default=DEFAULT_EFFORT,
        description='Thinking effort: "low", "medium", "high", false (off) or true',
    )

    @field_validator("think", mode="before")
    @classmethod
    def _off_means_false(cls, value: Any) -> Any:
        """`/effort off` and `think = "off"` both mean no thinking."""
        return False if isinstance(value, str) and value.lower() == "off" else value


class AppConfig(BaseModel):
    """Everything `sensai.toml` can set."""

    interface: Literal["cli", "tui", "web"] = Field(
        default=DEFAULT_INTERFACE,
        description="Interface started by `sensai chat`",
        json_schema_extra=RESTART,
    )
    provider: str = Field(default=DEFAULT_PROVIDER, description="ollama, groq or mock")
    model: str = Field(default=DEFAULT_MODEL, description="Model name for the provider")
    base_url: str = Field(default=DEFAULT_BASE_URL, description="Ollama server URL")
    api_key: str | None = Field(
        default=None, description="Groq key (prefer the GROQ_API_KEY variable)"
    )
    autosave: bool = Field(
        default=True,
        description="Write each change made in a session (/config set, /model, "
        "/provider, /effort, /persona) to the config file at once",
    )
    tools: ToolsConfig = ToolsConfig()
    budget: BudgetConfig = BudgetConfig()
    guardrails: GuardrailsConfig = GuardrailsConfig()
    eval: EvalConfig = EvalConfig()
    mcp: McpConfig = McpConfig()
    memory: MemoryConfig = MemoryConfig()
    reasoning: ReasoningConfig = ReasoningConfig()
    persona: PersonaConfig = PersonaConfig()
    rag: RagConfig = RagConfig()
    options: ModelOptions = Field(
        default_factory=lambda: ModelOptions(num_ctx=DEFAULT_NUM_CTX),
        description="Model options; num_ctx matches budget.max_tokens so Ollama "
        "never cuts the prompt silently",
    )

    @field_validator("options", mode="before")
    @classmethod
    def _default_window(cls, value: Any) -> Any:
        """An `[options]` table without num_ctx still gets the default window."""
        if isinstance(value, dict) and "num_ctx" not in value:
            return {**value, "num_ctx": DEFAULT_NUM_CTX}
        return value

    @model_validator(mode="after")
    def _budget_fits_context(self) -> "AppConfig":
        check_context_fits(self.budget, self.options)
        return self


def check_context_fits(budget: BudgetConfig, options: ModelOptions) -> None:
    """Past `num_ctx` Ollama silently drops the start of the prompt (system notes)."""
    if options.num_ctx is None:
        return
    room = options.num_ctx - (options.num_predict or 0)
    if budget.max_tokens > room:
        raise ValueError(
            f"budget.max_tokens ({budget.max_tokens}) must not exceed "
            f"options.num_ctx - options.num_predict ({room})"
        )


def validation_reasons(exc: ValidationError) -> str:
    """Pydantic errors as one line: `options.num_ctx: Input should be greater than 0`."""
    reasons = []
    for err in exc.errors():
        message = err["msg"].removeprefix("Value error, ")
        location = ".".join(map(str, err["loc"]))
        reasons.append(f"{location}: {message}" if location else message)
    return "; ".join(reasons)


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

    overrides = {
        "interface": interface,
        "provider": provider,
        "model": model,
        "base_url": base_url,
    }
    merged = {**file_data, **{k: v for k, v in overrides.items() if v is not None}}

    try:
        return AppConfig(**merged)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config values: {validation_reasons(exc)}") from exc


def to_file_value(key: str, value: Any) -> Any:
    """How a value is written to TOML; None means the key is left out."""
    if key == "tools.fs_allowed_root" and value is None:
        return False
    return value


def save_config(
    config: AppConfig,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> None:
    """Write every setting that differs from its default, or that the file already
    sets, into the file. Comments, key order and unknown keys are kept; settings
    left unset are removed, MCP servers missing from `config` too."""
    path = Path(config_path)
    tree = read_document(path).unwrap()
    defaults = flatten(AppConfig().model_dump(exclude={"mcp"}))
    current = flatten(config.model_dump(exclude={"mcp"}))
    in_file = flatten(tree)

    values: dict[str, Any] = {}
    removed: list[str] = []
    for key, value in current.items():
        stored = to_file_value(key, value)
        if stored is None:
            removed.append(key)
        elif value != defaults.get(key) or key in in_file:
            values[key] = stored

    servers = config.mcp.model_dump()["servers"]
    known = tree.get("mcp", {}).get("servers", {})
    for name, server in servers.items():
        if known.get(name) != server:
            values[f"mcp.servers.{name}"] = server
    removed.extend(f"mcp.servers.{name}" for name in known if name not in servers)

    update_file(path, values, removed)

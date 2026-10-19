import json
import re
from pathlib import Path
from typing import Any, Literal

import tomllib
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from sensai.core.budget import BudgetConfig
from sensai.domain.models import ModelOptions

DEFAULT_INTERFACE = "cli"
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "qwen3.5:4b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_CONFIG_PATH = Path("sensai.toml")
DEFAULT_EFFORT = "low"
_SERVER_NAME = re.compile(r"[A-Za-z0-9_-]+")


class ConfigError(Exception):
    """Raised when a config file exists but cannot be parsed or validated."""


class ToolsConfig(BaseModel):
    # "." is resolved against the directory Sensai is launched from.
    fs_allowed_root: str | None = "."
    web_search: bool = True
    sandbox: bool = True

    @field_validator("fs_allowed_root", mode="before")
    @classmethod
    def _false_disables_fs_tools(cls, value: Any) -> Any:
        # TOML has no null: `fs_allowed_root = false` turns the fs tools off.
        return None if value is False else value


class GuardrailsConfig(BaseModel):
    """Privacy/content guardrails (EV2). On by default; `enabled = false` opts out."""

    enabled: bool = True
    injection: Literal["block", "flag"] = "block"
    pii: Literal["redact", "block"] = "redact"


class EvalConfig(BaseModel):
    """Opt-in logs: replies (EV1, graded with `python -m sensai.eval.judge`) and the
    full prompt of every model call."""

    log_replies: bool = False
    replies_path: str = "logs/replies.jsonl"
    log_prompts: bool = False
    prompts_path: str = "logs/prompts.jsonl"


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

    servers: dict[str, McpServerConfig] = {}

    @field_validator("servers")
    @classmethod
    def _names_are_identifiers(
        cls, servers: dict[str, McpServerConfig]
    ) -> dict[str, McpServerConfig]:
        # Tool names reach the model as `<name>__<tool>`; keep them function-safe.
        for name in servers:
            if not _SERVER_NAME.fullmatch(name):
                raise ValueError(
                    f"invalid MCP server name {name!r}: use letters, digits, '-', '_'"
                )
        return servers


class MemoryConfig(BaseModel):
    """Structured long-term memory (M3). On by default; `enabled = false` opts out."""

    enabled: bool = True
    auto_inject: bool = True


class PersonaConfig(BaseModel):
    """Domain system prompt placed first in every call. Off by default."""

    enabled: bool = False
    name: str = "Sensai"
    instruction: str | None = None
    # Path to a text file holding the instruction, resolved from the launch directory.
    file: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> "PersonaConfig":
        if self.instruction is not None and self.file is not None:
            raise ValueError("set either instruction or file, not both")
        if self.enabled and self.instruction is None and self.file is None:
            raise ValueError("enabled persona needs an instruction or a file")
        return self


class RagConfig(BaseModel):
    """Local document retrieval. Off by default; `--rag-dir` also turns it on."""

    enabled: bool = False
    dir: str | None = None
    model: str = "nomic-embed-text"
    db: str = "rag.db"
    top_k: int = Field(default=5, ge=1)
    chunk_size: int = Field(default=500, gt=0)
    chunk_overlap: int = Field(default=50, ge=0)

    @model_validator(mode="after")
    def _coherent(self) -> "RagConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.enabled and not self.dir:
            raise ValueError("enabled RAG needs a dir")
        return self


class ReasoningConfig(BaseModel):
    """Visible reasoning loop: thoughts and steps between tool calls."""

    enabled: bool = True
    show_thoughts: bool = False
    max_steps: int = Field(default=5, ge=1)
    think: bool | str | None = DEFAULT_EFFORT


class AppConfig(BaseModel):
    interface: Literal["cli", "tui", "web"] = DEFAULT_INTERFACE
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    # Only providers that need a key (Groq) read it; GROQ_API_KEY works too.
    api_key: str | None = None
    tools: ToolsConfig = ToolsConfig()
    budget: BudgetConfig = BudgetConfig()
    guardrails: GuardrailsConfig = GuardrailsConfig()
    eval: EvalConfig = EvalConfig()
    mcp: McpConfig = McpConfig()
    memory: MemoryConfig = MemoryConfig()
    reasoning: ReasoningConfig = ReasoningConfig()
    persona: PersonaConfig = PersonaConfig()
    rag: RagConfig = RagConfig()
    options: ModelOptions = ModelOptions()

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
        reasons = "; ".join(
            ".".join(map(str, err["loc"])) + f": {err['msg']}"
            if err["loc"]
            else err["msg"]
            for err in exc.errors()
        )
        raise ConfigError(f"Invalid config values: {reasons}") from exc


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
    if config.api_key:
        lines.append(f"api_key = {json.dumps(config.api_key, ensure_ascii=False)}")

    if config.tools != ToolsConfig():
        # json.dumps(False) is "false", which loads back as None.
        fs_allowed_root = config.tools.fs_allowed_root or False
        lines.extend(
            [
                "",
                "[tools]",
                "fs_allowed_root = " + json.dumps(fs_allowed_root, ensure_ascii=False),
                f"web_search = {json.dumps(config.tools.web_search)}",
                f"sandbox = {json.dumps(config.tools.sandbox)}",
            ]
        )

    if config.rag != RagConfig():
        rag = config.rag
        lines.extend(["", "[rag]", f"enabled = {json.dumps(rag.enabled)}"])
        if rag.dir is not None:
            lines.append(f"dir = {json.dumps(rag.dir, ensure_ascii=False)}")
        lines.extend(
            [
                f"model = {json.dumps(rag.model, ensure_ascii=False)}",
                f"db = {json.dumps(rag.db, ensure_ascii=False)}",
                f"top_k = {rag.top_k}",
                f"chunk_size = {rag.chunk_size}",
                f"chunk_overlap = {rag.chunk_overlap}",
            ]
        )

    if config.budget != BudgetConfig():
        lines.extend(
            [
                "",
                "[budget]",
                f"max_tokens = {config.budget.max_tokens}",
                f"threshold = {config.budget.threshold}",
                f"keep_recent_turns = {config.budget.keep_recent_turns}",
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

    if config.eval != EvalConfig():
        lines.extend(
            [
                "",
                "[eval]",
                f"log_replies = {json.dumps(config.eval.log_replies)}",
                "replies_path = "
                + json.dumps(config.eval.replies_path, ensure_ascii=False),
                f"log_prompts = {json.dumps(config.eval.log_prompts)}",
                "prompts_path = "
                + json.dumps(config.eval.prompts_path, ensure_ascii=False),
            ]
        )

    if config.memory != MemoryConfig():
        lines.extend(
            [
                "",
                "[memory]",
                f"enabled = {json.dumps(config.memory.enabled)}",
                f"auto_inject = {json.dumps(config.memory.auto_inject)}",
            ]
        )

    if config.reasoning != ReasoningConfig():
        lines.extend(
            [
                "",
                "[reasoning]",
                f"enabled = {json.dumps(config.reasoning.enabled)}",
                f"show_thoughts = {json.dumps(config.reasoning.show_thoughts)}",
                f"max_steps = {config.reasoning.max_steps}",
            ]
        )
        if config.reasoning.think is not None:
            lines.append(f"think = {json.dumps(config.reasoning.think)}")

    if config.persona != PersonaConfig():
        persona = config.persona
        lines.extend(
            [
                "",
                "[persona]",
                f"enabled = {json.dumps(persona.enabled)}",
                f"name = {json.dumps(persona.name, ensure_ascii=False)}",
            ]
        )
        for key in ("instruction", "file"):
            if (value := getattr(persona, key)) is not None:
                lines.append(f"{key} = {json.dumps(value, ensure_ascii=False)}")

    if options := config.options.to_payload():
        lines.extend(["", "[options]"])
        lines.extend(f"{key} = {json.dumps(value)}" for key, value in options.items())

    # save_config rewrites the whole file, so every section must be written back or
    # a runtime /model would silently delete the user's MCP servers.
    for name, server in config.mcp.servers.items():
        lines.extend(
            [
                "",
                f"[mcp.servers.{name}]",
                f"command = {json.dumps(server.command, ensure_ascii=False)}",
                f"args = {json.dumps(server.args, ensure_ascii=False)}",
                f"timeout = {server.timeout}",
            ]
        )
        if server.env:
            lines.append(f"[mcp.servers.{name}.env]")
            lines.extend(
                f"{json.dumps(key, ensure_ascii=False)} = "
                f"{json.dumps(value, ensure_ascii=False)}"
                for key, value in server.env.items()
            )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not write config file {path}: {exc}") from exc

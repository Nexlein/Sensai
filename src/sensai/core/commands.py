import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from sensai.core.components import BootstrapError, apply_setting
from sensai.core.config import (
    DEFAULT_EFFORT,
    AppConfig,
    ConfigError,
    save_config,
    to_file_value,
)
from sensai.core.engine import ChatEngine
from sensai.core.prompt import format_prompt
from sensai.core.settings import (
    SETTINGS,
    assign,
    format_keys,
    format_settings,
    format_value,
    get_value,
    save_setting,
    sources,
    validated,
)
from sensai.domain.errors import ProviderError
from sensai.domain.events import Event
from sensai.domain.models import Conversation, Fact, LoadedModel
from sensai.domain.protocols import (
    LLMProvider,
    MemoryStore,
    ModelInspector,
    StructuredMemory,
    ToolRegistry,
)

ReadInputFn = Callable[[], str]
ProviderFactory = Callable[..., LLMProvider]
ToolRegistryFactory = Callable[[str | None], ToolRegistry]
RenderFn = Callable[[AsyncIterator[Event]], Awaitable[None]]
ErrorFn = Callable[[Exception], None]
ChoiceFn = Callable[
    [str, Sequence[str], str | None, Mapping[str, str]], Awaitable[str | None]
]


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    arguments: tuple[str, ...]


@dataclass
class CommandResult:
    message: str | None = None
    should_exit: bool = False


@dataclass
class CommandContext:
    """Everything a slash command may read or change in the running session.

    `config_path` is the file `/config` edits (None: nothing is ever written),
    `unsaved` the keys changed while autosave was off, `startup_warnings` the
    non-fatal problems met while building the session, and `closers` what to
    await when it ends (MCP server processes).
    """

    config: AppConfig
    engine: ChatEngine
    provider_factory: ProviderFactory
    tool_registry: ToolRegistry
    tool_registry_factory: ToolRegistryFactory
    memory_store: MemoryStore
    structured_memory: StructuredMemory | None = None
    config_path: Path | None = None
    startup_warnings: list[str] = field(default_factory=list)
    closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)
    choose: ChoiceFn | None = None
    unsaved: set[str] = field(default_factory=set)

    async def aclose(self) -> None:
        await asyncio.gather(*(close() for close in self.closers))


CommandHandler = Callable[[CommandContext, tuple[str, ...]], Awaitable[CommandResult]]


@dataclass(frozen=True)
class CommandSpec:
    handler: CommandHandler
    description: str


class SettingError(Exception):
    """A setting could not be changed; the message says why, in one line."""


def _persist(context: CommandContext, key: str, reset: bool) -> str | None:
    """Write `key` to the config file when autosave is on; the note to show."""
    path, config = context.config_path, context.config
    if path is None:
        return None
    if not config.autosave and key != "autosave":
        context.unsaved.add(key)
        return "not saved, /config save keeps it"
    try:
        save_setting(config, key, path, reset)
    except ConfigError as exc:
        context.unsaved.add(key)
        return f"not saved: {exc}"
    context.unsaved.discard(key)
    return f"saved to {path}"


def change_setting(context: CommandContext, key: str, raw: str | None) -> list[str]:
    """Validate, apply to the running session, then save one setting.

    `raw` is user text parsed like a TOML value; None resets the default. On any
    failure the previous value stays in place and SettingError explains why.
    Returns the notes to show after the new value.
    """
    config = context.config
    try:
        candidate = validated(config, key, raw)
    except ConfigError as exc:
        raise SettingError(str(exc)) from exc
    previous = config.model_copy(deep=True)
    assign(config, key, candidate)
    try:
        note = apply_setting(context, key)
    except (ProviderError, BootstrapError) as exc:
        assign(config, key, previous)
        raise SettingError(str(exc)) from exc
    saved = _persist(context, key, reset=raw is None)
    return [text for text in (note, saved) if text]


def _with_notes(message: str, notes: list[str]) -> str:
    return f"{message} ({'; '.join(notes)})" if notes else message


async def handle_provider(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    if len(arguments) != 1:
        return CommandResult(message="Usage: /provider <name>")

    provider_name = arguments[0].lower()
    try:
        notes = change_setting(context, "provider", provider_name)
    except SettingError as exc:
        return CommandResult(message=str(exc))
    return CommandResult(
        message=_with_notes(f"Provider switched to {provider_name}.", notes)
    )


async def handle_model(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    if len(arguments) != 1:
        return CommandResult(message="Usage: /model <name>")

    model_name = arguments[0]
    try:
        notes = change_setting(context, "model", model_name)
    except SettingError as exc:
        return CommandResult(message=f"Could not switch model: {exc}")
    return CommandResult(message=_with_notes(f"Model switched to {model_name}.", notes))


EFFORT_LEVELS = ("low", "medium", "high", "off")
EFFORT_USAGE = "Usage: /effort [low|medium|high|off]"


def _effort_name(think: bool | str | None) -> str:
    if think is False:
        return "off"
    if think is None or think is True:
        return "default"
    return think


async def handle_effort(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    """Show or set the thinking effort sent to the model."""
    reasoning = context.config.reasoning
    current = _effort_name(reasoning.think)
    if len(arguments) > 1:
        return CommandResult(message=EFFORT_USAGE)

    if arguments:
        name = arguments[0].lower()
    elif context.choose is None:
        return CommandResult(message=f"Effort: {current}. {EFFORT_USAGE}")
    else:
        picked = await context.choose(
            "Thinking effort",
            EFFORT_LEVELS,
            current,
            {DEFAULT_EFFORT: "default"},
        )
        if picked is None:
            return CommandResult(message=f"Effort unchanged: {current}.")
        name = picked

    if name not in EFFORT_LEVELS:
        return CommandResult(message=EFFORT_USAGE)
    try:
        notes = change_setting(context, "reasoning.think", f'"{name}"')
    except SettingError as exc:
        return CommandResult(message=str(exc))
    note = "" if reasoning.enabled else " Reasoning is disabled, so it has no effect."
    return CommandResult(message=_with_notes(f"Effort set to {name}.{note}", notes))


PERSONA_USAGE = "Usage: /persona [on|off]"


async def handle_persona(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    """Show or switch the domain system prompt, e.g. for a generic vs persona A/B."""
    engine = context.engine
    if len(arguments) > 1:
        return CommandResult(message=PERSONA_USAGE)
    if engine.persona is None:
        return CommandResult(
            message="No persona configured: set [persona] instruction or file."
        )

    notes: list[str] = []
    if arguments:
        choice = arguments[0].lower()
        if choice not in {"on", "off"}:
            return CommandResult(message=PERSONA_USAGE)
        try:
            notes = change_setting(
                context, "persona.enabled", "true" if choice == "on" else "false"
            )
        except SettingError as exc:
            return CommandResult(message=str(exc))

    state = "on" if engine.persona_enabled else "off"
    return CommandResult(
        message=_with_notes(f"Persona {engine.persona.name}: {state}.", notes)
    )


CONFIG_USAGE = (
    "Usage: /config [show [key]] | get <key> | set <key> <value> | reset <key> "
    "| keys [key] | save"
)


def _config_header(context: CommandContext) -> str:
    path = context.config_path
    if path is None:
        return "No config file: changes last for this session only."
    autosave = "on" if context.config.autosave else "off"
    header = f"Config file: {path} · autosave {autosave}"
    if context.unsaved:
        header += f" · unsaved: {', '.join(sorted(context.unsaved))}"
    return header


def _show(context: CommandContext, prefix: str | None) -> CommandResult:
    found = sources(context.config, context.config_path, context.unsaved)
    try:
        body = format_settings(context.config, found, prefix)
    except ConfigError as exc:
        return CommandResult(message=str(exc))
    return CommandResult(message=f"{_config_header(context)}\n\n{body}")


def _get(context: CommandContext, key: str) -> CommandResult:
    if key not in SETTINGS:
        return _show(context, key)
    value = get_value(context.config, key)
    return CommandResult(
        message=f"{key} = {format_value(key, to_file_value(key, value))}"
    )


def _set(context: CommandContext, key: str, raw: str | None) -> CommandResult:
    try:
        notes = change_setting(context, key, raw)
    except SettingError as exc:
        return CommandResult(message=str(exc))
    value = to_file_value(key, get_value(context.config, key))
    return CommandResult(
        message=_with_notes(f"{key} = {format_value(key, value)}", notes)
    )


def _save(context: CommandContext) -> CommandResult:
    if context.config_path is None:
        return CommandResult(message="No config file to save to.")
    try:
        save_config(context.config, context.config_path)
    except ConfigError as exc:
        return CommandResult(message=str(exc))
    context.unsaved.clear()
    return CommandResult(message=f"Config saved to {context.config_path}.")


async def handle_config(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    """Show, explain, change, reset or save settings by dotted key."""
    action, rest = (arguments[0].lower(), arguments[1:]) if arguments else ("show", ())

    if action in {"show", "get"} and len(rest) <= 1:
        if action == "get" and rest:
            return _get(context, rest[0])
        return _show(context, rest[0] if rest else None)
    if action == "keys" and len(rest) <= 1:
        try:
            return CommandResult(message=format_keys(rest[0] if rest else None))
        except ConfigError as exc:
            return CommandResult(message=str(exc))
    if action == "set":
        if len(rest) < 2:
            return CommandResult(message="Usage: /config set <key> <value>")
        return _set(context, rest[0], " ".join(rest[1:]))
    if action == "reset":
        if len(rest) != 1:
            return CommandResult(message="Usage: /config reset <key>")
        return _set(context, rest[0], None)
    if action == "save":
        if rest:
            return CommandResult(message="Usage: /config save")
        return _save(context)
    return CommandResult(message=CONFIG_USAGE)


async def handle_new(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    if arguments:
        return CommandResult(message="Usage: /new")

    conversation = Conversation()
    await context.memory_store.save(conversation)
    context.engine.conversation = conversation
    return CommandResult(message=f"Started new conversation: {conversation.id}")


async def handle_clear(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    context.engine.conversation.messages.clear()
    await context.memory_store.save(context.engine.conversation)
    return CommandResult(message="Conversation cleared.")


def _human_bytes(size: int) -> str:
    """Decimal units, rounded like `ollama ps`."""
    value, unit = float(size), "B"
    for next_unit in ("KB", "MB", "GB", "TB"):
        if value < 1000:
            break
        value, unit = value / 1000, next_unit
    if value >= 10 or value == int(value):
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def _processor(model: LoadedModel) -> str:
    if model.size_vram == 0:
        return "100% CPU"
    if model.size_vram == model.size:
        return "100% GPU"
    if model.size_vram > model.size:
        return "unknown"
    cpu = round((model.size - model.size_vram) / model.size * 100)
    return f"{cpu}%/{100 - cpu}% CPU/GPU"


def format_loaded_model(model: LoadedModel) -> str:
    parts = [model.name, _human_bytes(model.size), _processor(model)]
    if model.context_length:
        parts.append(f"ctx {model.context_length}")
    return " · ".join(parts)


async def handle_ps(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    """Show the RAM/VRAM held by each model the server has loaded."""
    provider = context.engine.provider
    if not isinstance(provider, ModelInspector):
        return CommandResult(message="/ps is not available for this provider.")
    try:
        models = await provider.loaded_models()
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        return CommandResult(message=f"Could not read loaded models: {exc}")
    if not models:
        return CommandResult(message="No model loaded.")
    return CommandResult(message="\n".join(map(format_loaded_model, models)))


async def handle_prompt(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    """Show the prompt of the latest model call, message by message."""
    engine = context.engine
    if not engine.last_prompt:
        return CommandResult(message="No prompt sent yet.")
    max_tokens = engine.budget.config.max_tokens if engine.budget else None
    return CommandResult(message=format_prompt(engine.last_prompt, max_tokens))


async def handle_help(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    lines = ["Available commands:"]
    lines.extend(
        f"/{name} - {command.description}" for name, command in COMMANDS.items()
    )
    return CommandResult(message="\n".join(lines))


async def handle_exit(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    return CommandResult(should_exit=True)


def _format_fact_line(fact: Fact, bullet: bool = True) -> str:
    tags_str = f" [{', '.join(fact.tags)}]" if fact.tags else ""
    prefix = "• " if bullet else ""
    return f"{prefix}{fact.entity_name}.{fact.key} = {fact.value}{tags_str}"


def _mem_list(mem: StructuredMemory, args: tuple[str, ...]) -> CommandResult:
    entity_filter = args[0] if args else None
    facts = mem.list_facts(entity=entity_filter)
    if not facts:
        return CommandResult(message="No memories stored.")
    lines = ["Stored memories:", *(_format_fact_line(f) for f in facts)]
    return CommandResult(message="\n".join(lines))


def _mem_get(mem: StructuredMemory, args: tuple[str, ...]) -> CommandResult:
    if len(args) != 2:
        return CommandResult(message="Usage: /memory get <entity> <key>")
    fact = mem.get_fact(args[0], args[1])
    if fact is None:
        return CommandResult(message=f"Memory not found: {args[0]}.{args[1]}")
    return CommandResult(message=_format_fact_line(fact, bullet=False))


def _mem_set(mem: StructuredMemory, args: tuple[str, ...]) -> CommandResult:
    if len(args) < 3:
        return CommandResult(message="Usage: /memory set <entity> <key> <value>")
    fact = mem.store_fact(args[0], args[1], " ".join(args[2:]))
    return CommandResult(message=f"Saved: {fact.entity_name}.{fact.key} = {fact.value}")


def _mem_delete(mem: StructuredMemory, args: tuple[str, ...]) -> CommandResult:
    if len(args) != 2:
        return CommandResult(message="Usage: /memory delete <entity> <key>")
    if mem.delete_fact(args[0], args[1]):
        return CommandResult(message=f"Deleted memory: {args[0]}.{args[1]}")
    return CommandResult(message=f"Memory not found: {args[0]}.{args[1]}")


def _mem_search(mem: StructuredMemory, args: tuple[str, ...]) -> CommandResult:
    if not args:
        return CommandResult(message="Usage: /memory search <query>")
    query = " ".join(args)
    facts = mem.search_facts(query)
    if not facts:
        return CommandResult(message=f"No memories matching '{query}'.")
    lines = [f"Memories matching '{query}':", *(_format_fact_line(f) for f in facts)]
    return CommandResult(message="\n".join(lines))


def _mem_clear(mem: StructuredMemory, _args: tuple[str, ...]) -> CommandResult:
    mem.clear()
    return CommandResult(message="All structured memories cleared.")


MEMORY_SUBCOMMANDS: dict[
    str, Callable[[StructuredMemory, tuple[str, ...]], CommandResult]
] = {
    "list": _mem_list,
    "get": _mem_get,
    "set": _mem_set,
    "delete": _mem_delete,
    "search": _mem_search,
    "clear": _mem_clear,
}

MEMORY_USAGE = (
    "Usage: /memory [list [entity]] | /memory get <entity> <key> | "
    "/memory set <entity> <key> <value> | /memory delete <entity> <key> | "
    "/memory search <query> | /memory clear"
)


async def handle_memory(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    mem = context.structured_memory or getattr(context.engine, "memory", None)
    if mem is None:
        return CommandResult(message="Structured memory is not available.")

    subcmd = arguments[0].lower() if arguments else "list"
    handler = MEMORY_SUBCOMMANDS.get(subcmd)
    if handler is None:
        return CommandResult(message=MEMORY_USAGE)

    sub_args = arguments[1:] if arguments else ()
    return handler(mem, sub_args)


COMMANDS = {
    "exit": CommandSpec(handle_exit, "Exit the interactive session"),
    "help": CommandSpec(handle_help, "Show available commands"),
    "clear": CommandSpec(handle_clear, "Clear the current conversation history"),
    "new": CommandSpec(handle_new, "Start and persist a new conversation"),
    "memory": CommandSpec(
        handle_memory, "Inspect or manage long-term structured memory"
    ),
    "model": CommandSpec(handle_model, "Switch model for subsequent turns"),
    "effort": CommandSpec(handle_effort, "Show or set the thinking effort"),
    "provider": CommandSpec(handle_provider, "Switch LLM provider"),
    "persona": CommandSpec(handle_persona, "Show or switch the domain persona"),
    "config": CommandSpec(handle_config, "Show, change, reset or save settings"),
    "prompt": CommandSpec(handle_prompt, "Show the full prompt of the last model call"),
    "ps": CommandSpec(handle_ps, "Show RAM/VRAM used by the loaded models"),
}


async def dispatch_command(
    command: ParsedCommand,
    context: CommandContext,
) -> CommandResult:
    registered_command = COMMANDS.get(command.name)

    if registered_command is None:
        return CommandResult(message=f"Unknown command: /{command.name}")

    return await registered_command.handler(context, command.arguments)


def parse_commands(text: str) -> ParsedCommand | None:
    stripped = text.strip()

    if not stripped.startswith("/"):
        return None

    parts = stripped[1:].split()

    if not parts:
        return None

    return ParsedCommand(
        name=parts[0].lower(),
        arguments=tuple(parts[1:]),
    )

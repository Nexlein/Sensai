import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from sensai.core.config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_EFFORT,
    AppConfig,
    ConfigError,
    save_config,
)
from sensai.core.engine import ChatEngine
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
    config: AppConfig
    engine: ChatEngine
    provider_factory: ProviderFactory
    tool_registry: ToolRegistry
    tool_registry_factory: ToolRegistryFactory
    memory_store: MemoryStore
    structured_memory: StructuredMemory | None = None
    config_path: Path = DEFAULT_CONFIG_PATH
    # Non-fatal problems found while building the session, shown once at startup.
    startup_warnings: list[str] = field(default_factory=list)
    # Awaited when the session ends, e.g. to stop MCP server processes.
    closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)
    choose: ChoiceFn | None = None

    async def aclose(self) -> None:
        await asyncio.gather(*(close() for close in self.closers))


CommandHandler = Callable[[CommandContext, tuple[str, ...]], Awaitable[CommandResult]]


@dataclass(frozen=True)
class CommandSpec:
    handler: CommandHandler
    description: str


async def handle_provider(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    if len(arguments) != 1:
        return CommandResult(message="Usage: /provider <name>")

    provider_name = arguments[0].lower()

    try:
        new_provider = context.provider_factory(
            provider_name,
            model=context.config.model,
            base_url=context.config.base_url,
            api_key=context.config.api_key,
        )
    except ProviderError as exc:
        return CommandResult(message=str(exc))

    context.engine.provider = new_provider
    context.config.provider = provider_name
    return CommandResult(message=f"Provider switched to {provider_name}.")


async def handle_model(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    if len(arguments) != 1:
        return CommandResult(message="Usage: /model <name>")

    model_name = arguments[0]
    try:
        new_provider = context.provider_factory(
            context.config.provider,
            model=model_name,
            base_url=context.config.base_url,
            api_key=context.config.api_key,
        )
    except ProviderError as exc:
        return CommandResult(message=f"Could not switch model: {exc}")
    context.engine.provider = new_provider
    context.config.model = model_name
    return CommandResult(message=f"Model switched to {model_name}.")


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
    reasoning.think = False if name == "off" else name
    context.engine.think = reasoning.think
    note = "" if reasoning.enabled else " Reasoning is disabled, so it has no effect."
    return CommandResult(message=f"Effort set to {name}.{note}")


async def handle_base_url(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    if len(arguments) != 1:
        return CommandResult(message="Usage: /config set base_url <url>")

    base_url = arguments[0]
    try:
        new_provider = context.provider_factory(
            context.config.provider,
            model=context.config.model,
            base_url=base_url,
            api_key=context.config.api_key,
        )
    except ProviderError as exc:
        return CommandResult(message=f"Could not update base_url: {exc}")

    context.engine.provider = new_provider
    context.config.base_url = base_url
    return CommandResult(message=f"base_url = {base_url}")


async def handle_fs_allowed_root(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    if len(arguments) != 1:
        return CommandResult(
            message="Usage: /config set tools.fs_allowed_root <path|none>"
        )

    value = arguments[0]
    allowed_root = None if value.lower() in {"none", "null", "off"} else value
    registry = context.tool_registry_factory(allowed_root)

    context.tool_registry = registry
    context.engine.registry = registry
    context.config.tools.fs_allowed_root = allowed_root
    return CommandResult(message=f"tools.fs_allowed_root = {allowed_root}")


CONFIG_SETTERS = {
    "model": handle_model,
    "provider": handle_provider,
    "base_url": handle_base_url,
    "tools.fs_allowed_root": handle_fs_allowed_root,
}


async def handle_config(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> CommandResult:
    values = context.config.model_dump()
    if values["api_key"]:
        values["api_key"] = "***"

    if not arguments:
        return CommandResult(message=str(values))

    action = arguments[0]
    action_arguments = arguments[1:]

    if action == "get":
        if not action_arguments:
            return CommandResult(message=str(values))
        if len(action_arguments) != 1:
            return CommandResult(message="Usage: /config get [key]")

        key = action_arguments[0]
        value: object = values
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                return CommandResult(message=f"Unknown config key: {key}")
            value = value[part]

        return CommandResult(message=f"{key} = {value}")

    if action == "save":
        if action_arguments:
            return CommandResult(message="Usage: /config save")

        try:
            save_config(context.config, context.config_path)
        except ConfigError as exc:
            return CommandResult(message=str(exc))

        return CommandResult(message=f"Config saved to {context.config_path}.")

    if action == "set":
        if len(action_arguments) != 2:
            return CommandResult(message="Usage: /config set <key> <value>")

        key, value = action_arguments
        setter = CONFIG_SETTERS.get(key)
        if setter is None:
            return CommandResult(message=f"Unknown config key: {key}")

        return await setter(context, (value,))

    return CommandResult(
        message="Usage: /config get [key] | /config set <key> <value> | /config save"
    )


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
    "config": CommandSpec(handle_config, "View or update runtime configuration"),
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

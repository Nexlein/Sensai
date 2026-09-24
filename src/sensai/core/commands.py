from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from sensai.core.config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    ConfigError,
    save_config,
)
from sensai.core.engine import ChatEngine
from sensai.domain.errors import ProviderError
from sensai.domain.events import Event
from sensai.domain.models import Conversation
from sensai.domain.protocols import LLMProvider, MemoryStore, ToolRegistry

ReadInputFn = Callable[[], str]
ProviderFactory = Callable[..., LLMProvider]
ToolRegistryFactory = Callable[[str | None], ToolRegistry]
RenderFn = Callable[[AsyncIterator[Event]], Awaitable[None]]
ErrorFn = Callable[[Exception], None]


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
    config_path: Path = DEFAULT_CONFIG_PATH


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
        )
    except ProviderError as exc:
        return CommandResult(message=f"Could not switch model: {exc}")
    context.engine.provider = new_provider
    context.config.model = model_name
    return CommandResult(message=f"Model switched to {model_name}.")


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
    return CommandResult(message="Conversation cleared.")


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


COMMANDS = {
    "exit": CommandSpec(handle_exit, "Exit the interactive session"),
    "help": CommandSpec(handle_help, "Show available commands"),
    "clear": CommandSpec(handle_clear, "Clear the current conversation history"),
    "new": CommandSpec(handle_new, "Start and persist a new conversation"),
    "model": CommandSpec(handle_model, "Switch model for subsequent turns"),
    "provider": CommandSpec(handle_provider, "Switch LLM provider"),
    "config": CommandSpec(handle_config, "View or update runtime configuration"),
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

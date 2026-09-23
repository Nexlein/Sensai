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
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event
from sensai.domain.models import Conversation
from sensai.domain.protocols import LLMProvider, MemoryStore, ToolRegistry

ReadInputFn = Callable[[], str]
OutputFn = Callable[[str], None]
ProviderFactory = Callable[..., LLMProvider]
ToolRegistryFactory = Callable[[str | None], ToolRegistry]
RenderFn = Callable[[AsyncIterator[Event]], Awaitable[None]]
ErrorFn = Callable[[Exception], None]


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    arguments: tuple[str, ...]


@dataclass
class CommandContext:
    config: AppConfig
    engine: ChatEngine
    output: OutputFn
    provider_factory: ProviderFactory
    tool_registry: ToolRegistry
    tool_registry_factory: ToolRegistryFactory
    memory_store: MemoryStore
    config_path: Path = DEFAULT_CONFIG_PATH


CommandHandler = Callable[[CommandContext, tuple[str, ...]], Awaitable[bool]]


@dataclass(frozen=True)
class CommandSpec:
    handler: CommandHandler
    description: str


async def handle_provider(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> bool:
    if len(arguments) != 1:
        context.output("Usage: /provider <name>")
        return False

    provider_name = arguments[0].lower()

    try:
        new_provider = context.provider_factory(
            provider_name,
            model=context.config.model,
            base_url=context.config.base_url,
        )
    except ProviderError as exc:
        context.output(str(exc))
        return False

    context.engine.provider = new_provider
    context.config.provider = provider_name
    context.output(f"Provider switched to {provider_name}.")
    return False


async def handle_model(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> bool:
    if len(arguments) != 1:
        context.output("Usage: /model <name>")
        return False

    model_name = arguments[0]
    try:
        new_provider = context.provider_factory(
            context.config.provider,
            model=model_name,
            base_url=context.config.base_url,
        )
    except ProviderError as exc:
        context.output(f"Could not switch model: {exc}")
        return False
    context.engine.provider = new_provider
    context.config.model = model_name
    context.output(f"Model switched to {model_name}.")
    return False


async def handle_base_url(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> bool:
    if len(arguments) != 1:
        context.output("Usage: /config set base_url <url>")
        return False

    base_url = arguments[0]
    try:
        new_provider = context.provider_factory(
            context.config.provider,
            model=context.config.model,
            base_url=base_url,
        )
    except ProviderError as exc:
        context.output(f"Could not update base_url: {exc}")
        return False

    context.engine.provider = new_provider
    context.config.base_url = base_url
    context.output(f"base_url = {base_url}")
    return False


async def handle_fs_allowed_root(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> bool:
    if len(arguments) != 1:
        context.output("Usage: /config set tools.fs_allowed_root <path|none>")
        return False

    value = arguments[0]
    allowed_root = None if value.lower() in {"none", "null", "off"} else value
    registry = context.tool_registry_factory(allowed_root)

    context.tool_registry = registry
    context.engine.registry = registry
    context.config.tools.fs_allowed_root = allowed_root
    context.output(f"tools.fs_allowed_root = {allowed_root}")
    return False


CONFIG_SETTERS = {
    "model": handle_model,
    "provider": handle_provider,
    "base_url": handle_base_url,
    "tools.fs_allowed_root": handle_fs_allowed_root,
}


async def handle_config(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> bool:
    values = context.config.model_dump()

    if not arguments:
        context.output(str(values))
        return False

    action = arguments[0]
    action_arguments = arguments[1:]

    if action == "get":
        if not action_arguments:
            context.output(str(values))
            return False
        if len(action_arguments) != 1:
            context.output("Usage: /config get [key]")
            return False

        key = action_arguments[0]
        value: object = values
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                context.output(f"Unknown config key: {key}")
                return False
            value = value[part]

        context.output(f"{key} = {value}")
        return False

    if action == "save":
        if action_arguments:
            context.output("Usage: /config save")
            return False

        try:
            save_config(context.config, context.config_path)
        except ConfigError as exc:
            context.output(str(exc))
            return False

        context.output(f"Config saved to {context.config_path}.")
        return False

    if action == "set":
        if len(action_arguments) != 2:
            context.output("Usage: /config set <key> <value>")
            return False

        key, value = action_arguments
        setter = CONFIG_SETTERS.get(key)
        if setter is None:
            context.output(f"Unknown config key: {key}")
            return False

        return await setter(context, (value,))

    context.output(
        "Usage: /config get [key] | /config set <key> <value> | /config save"
    )
    return False


async def handle_new(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> bool:
    if arguments:
        context.output("Usage: /new")
        return False

    conversation = Conversation()
    await context.memory_store.save(conversation)
    context.engine.conversation = conversation
    context.output(f"Started new conversation: {conversation.id}")
    return False


async def handle_clear(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> bool:
    context.engine.conversation.messages.clear()
    context.output("Conversation cleared.")
    return False


async def handle_help(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> bool:
    lines = ["Available commands:"]
    lines.extend(
        f"/{name} - {command.description}" for name, command in COMMANDS.items()
    )
    context.output("\n".join(lines))
    return False


async def handle_exit(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> bool:
    return True


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
) -> bool:
    registered_command = COMMANDS.get(command.name)

    if registered_command is None:
        context.output(f"Unknown command: /{command.name}")
        return False

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
            should_exit = await dispatch_command(command, context)

            if should_exit:
                break
            continue
        try:
            await render(context.engine.send(text))
        except (EmptyInputError, ProviderError) as exc:
            on_error(exc)

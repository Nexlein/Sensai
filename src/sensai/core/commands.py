from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from sensai.core.config import AppConfig
from sensai.core.engine import ChatEngine
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event

ReadInputFn = Callable[[], str]
OutputFn = Callable[[str], None]
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
    context.output("Available commands: /exit, /help, /clear")
    return False


async def handle_exit(
    context: CommandContext,
    arguments: tuple[str, ...],
) -> bool:
    return True


COMMAND_HANDLERS = {
    "exit": handle_exit,
    "help": handle_help,
    "clear": handle_clear,
}

async def dispatch_command(
    command: ParsedCommand,
    context: CommandContext,
) -> bool:
    handler = COMMAND_HANDLERS.get(command.name)

    if handler is None:
        context.output(f"Unknown command: /{command.name}")
        return False

    return await handler(context, command.arguments)


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

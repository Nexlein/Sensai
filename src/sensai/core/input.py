"""Shared handling for one interactive input from any frontend."""

from sensai.core.commands import (
    CommandContext,
    CommandResult,
    RenderFn,
    dispatch_command,
    parse_commands,
)
from sensai.core.engine import ConfirmTool


async def process_input(
    context: CommandContext,
    text: str,
    render: RenderFn,
    confirm_tool: ConfirmTool | None = None,
) -> CommandResult:
    """Execute a slash command or stream a chat turn through the given renderer."""
    command = parse_commands(text)
    if command is not None:
        return await dispatch_command(command, context)

    await render(context.engine.send(text, confirm_tool=confirm_tool))
    await context.memory_store.save(context.engine.conversation)
    return CommandResult()

"""Textual frontend for a shared Sensai session."""

from sensai.core.commands import CommandContext, CommandResult, RenderFn
from sensai.core.engine import ConfirmTool
from sensai.core.input import process_input
from sensai.interfaces.tui.renderer import ChatApp


async def run_tui(context: CommandContext) -> None:
    async def submit(
        text: str, render: RenderFn, confirm_tool: ConfirmTool | None = None
    ) -> CommandResult:
        return await process_input(context, text, render, confirm_tool)

    await ChatApp(submit).run_async()

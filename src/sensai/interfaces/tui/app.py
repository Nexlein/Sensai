"""Textual frontend for a shared Sensai session."""

from sensai.core.commands import CommandContext, CommandResult, RenderFn
from sensai.core.input import process_input
from sensai.interfaces.tui.renderer import ChatApp


async def run_tui(context: CommandContext) -> None:
    async def submit(text: str, render: RenderFn) -> CommandResult:
        return await process_input(context, text, render)

    await ChatApp(submit).run_async()

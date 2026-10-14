"""Textual frontend for a shared Sensai session."""

from collections.abc import Mapping, Sequence

from sensai.core.commands import CommandContext, CommandResult, RenderFn
from sensai.core.input import process_input
from sensai.core.tool_runner import ConfirmTool
from sensai.interfaces.prompts import choice_question
from sensai.interfaces.tui.renderer import ChatApp


async def run_tui(context: CommandContext) -> None:
    async def submit(
        text: str, render: RenderFn, confirm_tool: ConfirmTool | None = None
    ) -> CommandResult:
        return await process_input(context, text, render, confirm_tool)

    app = ChatApp(submit, context.config.reasoning.show_thoughts)

    async def choose(
        title: str,
        labels: Sequence[str],
        current: str | None,
        notes: Mapping[str, str],
    ) -> str | None:
        return await app.ask(choice_question(title, labels, current, notes))

    context.choose = choose
    await app.run_async()

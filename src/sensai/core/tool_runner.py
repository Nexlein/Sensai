from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass

from sensai.core.guard import guardrail_event
from sensai.domain.events import Event
from sensai.domain.models import Conversation, ToolCall
from sensai.domain.protocols import BaseTool, Guardrail, ToolRegistry

TOOL_RESULT_WITHHELD = "[tool result withheld: it contained personal data]"
TOOL_DECLINED = "Tool execution declined by the user."
TOOL_CONFIRMATION_FAILED = "Tool confirmation failed; execution cancelled."

ConfirmTool = Callable[[ToolCall], Awaitable[bool]]


@dataclass
class ToolOutcome:
    result: str
    declined: bool = False


def preview(tool: BaseTool, tc: ToolCall) -> str | None:
    """What the tool would change, for the confirmation prompt; None if unknown."""
    build: Callable[..., str | None] | None = getattr(tool, "preview", None)
    if not callable(build):
        return None
    try:
        return build(**tc.arguments)
    except Exception:  # noqa: BLE001
        return None


class ToolRunner:
    """Runs the tools a model asked for and records their results.

    A preview is a convenience: failing to build it never blocks the prompt. A
    broken confirmation callback never authorizes a tool. Results are filtered
    like any model output before they reach the history.
    """

    def __init__(
        self,
        registry: ToolRegistry | None,
        guardrail: Guardrail | None,
        conversation: Conversation,
    ) -> None:
        self.registry = registry
        self.guardrail = guardrail
        self.conversation = conversation

    async def run(self, tc: ToolCall, confirm_tool: ConfirmTool | None) -> ToolOutcome:
        """Confirm if the tool asks for it, then execute it; errors become text."""
        tool = self.registry.get(tc.name) if self.registry else None
        if not tool:
            return ToolOutcome(f"Error: Tool '{tc.name}' not found in registry.")
        try:
            if tool.requires_confirmation:
                tc.preview = preview(tool, tc)
                try:
                    approved = confirm_tool is not None and await confirm_tool(tc)
                except Exception:  # noqa: BLE001
                    return ToolOutcome(TOOL_CONFIRMATION_FAILED, declined=True)
                if approved is not True:
                    return ToolOutcome(TOOL_DECLINED, declined=True)
            return ToolOutcome(str(await tool.execute(**tc.arguments)))
        except Exception as e:  # noqa: BLE001
            return ToolOutcome(str(e))

    async def store(self, content: str) -> AsyncGenerator[Event]:
        """Add a tool result to the history, filtered like any model output."""
        if self.guardrail is not None:
            verdict = await self.guardrail.filter_output(content)
            if verdict.action != "allow":
                yield guardrail_event("tool", verdict.action, verdict.findings)
            content = (
                TOOL_RESULT_WITHHELD if verdict.action == "block" else verdict.text
            )
        self.conversation.add_message(role="tool", content=content)

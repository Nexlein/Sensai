from dataclasses import dataclass, field

from sensai.domain.models import ToolCall


@dataclass
class Turn:
    """State shared by every step of one user turn.

    `user_text` is the text after the input guardrail: it is what the retriever
    embeds, what the provider sees and what the history stores. `masked` is True
    once something the model will see was replaced by a placeholder, so the model
    is told so (otherwise "[IBAN]" reads like a glitch). `declined` collects the
    names of the tools the user refused this step.
    """

    user_text: str
    rag_context: str = ""
    masked: bool = False
    declined: list[str] = field(default_factory=list)


@dataclass
class Round:
    """What the model produced in one provider call."""

    chunks: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    refused: bool = False
    native_thoughts: list[str] = field(default_factory=list)
    text_thought: str = ""

    @property
    def text(self) -> str:
        return "".join(self.chunks)

    @property
    def thought(self) -> str | None:
        """Native reasoning followed by the text written before the tool calls."""
        parts = ["".join(self.native_thoughts), self.text_thought.strip()]
        return "\n".join(part for part in parts if part) or None

    @property
    def message_text(self) -> str:
        """The text kept as message content: none when it became a thought."""
        return "" if self.text_thought else self.text

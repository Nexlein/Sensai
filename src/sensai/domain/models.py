from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def generate_uuid() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class ToolCall(BaseModel):
    id: str = Field(default_factory=generate_uuid)
    name: str
    arguments: dict[str, Any]
    # Unified diff shown before confirmation; display-only, never persisted.
    preview: str | None = Field(default=None, exclude=True)


class Message(BaseModel):
    id: str = Field(default_factory=generate_uuid)
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None
    thought: str | None = None
    timestamp: datetime = Field(default_factory=now_utc)


class Conversation(BaseModel):
    id: str = Field(default_factory=generate_uuid)
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    def add_message(
        self,
        role: Literal["system", "user", "assistant", "tool"],
        content: str,
        tool_calls: list[ToolCall] | None = None,
        thought: str | None = None,
    ) -> Message:
        msg = Message(
            role=role, content=content, tool_calls=tool_calls, thought=thought
        )
        self.messages.append(msg)
        self.updated_at = now_utc()
        return msg


class Persona(BaseModel):
    id: str
    name: str
    description: str
    system_instruction: str


class LoadedModel(BaseModel):
    """A model held in memory by the server, as `ollama ps` reports it."""

    name: str
    size: int  # bytes: weights + KV cache + buffers
    size_vram: int = 0  # bytes of `size` held in GPU memory
    context_length: int | None = None


class ModelOptions(BaseModel):
    """Sampling and context options sent to the model; unset keys are not sent."""

    temperature: float | None = Field(
        default=None, ge=0, description="Sampling temperature: 0 is repeatable"
    )
    num_ctx: int | None = Field(
        default=None,
        gt=0,
        description="Context window in tokens (Ollama's own default is 4096 here)",
    )
    top_p: float | None = Field(
        default=None, gt=0, le=1, description="Nucleus sampling cut-off"
    )
    seed: int | None = Field(default=None, description="Fixed seed for repeatable runs")
    num_predict: int | None = Field(
        default=None, gt=0, description="Maximum tokens in one reply"
    )

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


GuardrailAction = Literal["allow", "redact", "block", "flag"]


class GuardrailFinding(BaseModel):
    """A rule that matched. Never carries the matched value itself."""

    rule: str
    category: str


class GuardrailVerdict(BaseModel):
    """Outcome of a guardrail check.

    `text` is what callers must use in place of the original: redacted text
    for `redact`, unchanged text otherwise. On `block`, callers must not
    forward it anywhere.
    """

    action: GuardrailAction
    text: str
    findings: list[GuardrailFinding] = Field(default_factory=list)


class Document(BaseModel):
    """A raw document ingested from the filesystem."""

    id: str = Field(default_factory=generate_uuid)
    path: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """A segment of text split from a Document."""

    id: str = Field(default_factory=generate_uuid)
    doc_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class ScoredChunk(Chunk):
    """A retrieved Chunk augmented with a similarity score."""

    score: float


class Entity(BaseModel):
    """An entity stored in long-term memory (e.g. 'user', 'project')."""

    id: str = Field(default_factory=generate_uuid)
    name: str
    entity_type: str = "generic"
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class Fact(BaseModel):
    """A structured fact about an entity stored across sessions."""

    id: str = Field(default_factory=generate_uuid)
    entity_name: str
    key: str
    value: str
    confidence: float = 1.0
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

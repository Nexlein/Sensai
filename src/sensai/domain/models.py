from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def generate_uuid() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


ID = Annotated[str, Field(default_factory=generate_uuid)]
Now = Annotated[datetime, Field(default_factory=now_utc)]


class ToolCall(BaseModel):
    id: ID
    name: str
    arguments: dict[str, Any]
    # Unified diff shown before confirmation; display-only, never persisted.
    preview: str | None = Field(default=None, exclude=True)


class Message(BaseModel):
    id: ID
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None
    thought: str | None = None
    timestamp: Now


class Conversation(BaseModel):
    id: ID
    messages: list[Message] = Field(default_factory=list)
    created_at: Now
    updated_at: Now

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

    id: ID
    path: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """A segment of text split from a Document."""

    id: ID
    doc_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class ScoredChunk(Chunk):
    """A retrieved Chunk augmented with a similarity score."""

    score: float


class Entity(BaseModel):
    """An entity stored in long-term memory (e.g. 'user', 'project')."""

    id: ID
    name: str
    entity_type: str = "generic"
    created_at: Now
    updated_at: Now


class Fact(BaseModel):
    """A structured fact about an entity stored across sessions."""

    id: ID
    entity_name: str
    key: str
    value: str
    confidence: float = 1.0
    tags: list[str] = Field(default_factory=list)
    created_at: Now
    updated_at: Now

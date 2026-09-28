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


class Message(BaseModel):
    id: ID
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None
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
    ) -> Message:
        msg = Message(role=role, content=content, tool_calls=tool_calls)
        self.messages.append(msg)
        self.updated_at = now_utc()
        return msg


class Persona(BaseModel):
    id: str
    name: str
    description: str
    system_instruction: str


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

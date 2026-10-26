from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from sensai.domain.events import Event
from sensai.domain.models import (
    Chunk,
    Conversation,
    Fact,
    GuardrailFinding,
    GuardrailVerdict,
    LoadedModel,
    Message,
    ScoredChunk,
)


class LLMProvider(Protocol):
    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        *,
        think: bool | str | None = None,
    ) -> AsyncIterator[Event]: ...


@runtime_checkable
class ModelInspector(Protocol):
    """A provider that can report the models its server holds in memory."""

    async def loaded_models(self) -> list[LoadedModel]: ...


class BaseTool(Protocol):
    name: str
    description: str
    parameters_schema: dict[str, Any]
    requires_confirmation: bool

    async def execute(self, **kwargs: Any) -> str: ...


class MemoryStore(Protocol):
    async def save(self, conversation: Conversation) -> None: ...

    async def load(self, conversation_id: str) -> Conversation | None: ...


class OutputStream(Protocol):
    """Incremental output filter: PII may be split across chunks.

    `findings` accumulates what was redacted or refused, so the caller can report
    it after the stream ends. `refused` is True once the stream gave up on the
    reply: it then emits a refusal notice and swallows everything after it.
    """

    findings: list[GuardrailFinding]
    refused: bool

    def feed(self, chunk: str) -> str: ...

    def flush(self) -> str: ...


class Guardrail(Protocol):
    async def filter_input(self, text: str) -> GuardrailVerdict: ...

    async def filter_output(self, text: str) -> GuardrailVerdict: ...

    def new_output_stream(self) -> OutputStream: ...


class Summarizer(Protocol):
    async def summarize(self, messages: list[Message]) -> str: ...


class ToolRegistry(Protocol):
    def get(self, name: str) -> BaseTool | None: ...

    def get_tools_schema(self) -> list[dict[str, Any]]: ...


class EmbeddingProvider(Protocol):
    """Protocol for generating vector embeddings from text."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    def replace_chunks(self, chunks: list[Chunk]) -> None: ...

    def search(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[ScoredChunk]: ...


class ContextRetriever(Protocol):
    async def retrieve_context(self, query: str, top_k: int = 5) -> str: ...


class ReplyRecorder(Protocol):
    """Keeps each final reply with its question and RAG context, for later grading."""

    def record(self, question: str, answer: str, context: str) -> None: ...


class PromptRecorder(Protocol):
    """Keeps each prompt exactly as sent to the model, one entry per model call."""

    def record_prompt(self, entry: dict[str, Any]) -> None: ...


class StructuredMemory(Protocol):
    """External structured memory (M3): CRUD over entities and facts across sessions."""

    def store_fact(
        self,
        entity: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        tags: list[str] | None = None,
        entity_type: str = "generic",
    ) -> Fact: ...

    def get_fact(self, entity: str, key: str) -> Fact | None: ...

    def list_facts(
        self, entity: str | None = None, tag: str | None = None
    ) -> list[Fact]: ...

    def search_facts(self, query: str) -> list[Fact]: ...

    def delete_fact(self, entity: str, key: str) -> bool: ...

    def delete_entity(self, entity: str) -> bool: ...

    def clear(self) -> None: ...

    def format_context(self, entity: str | None = None, max_facts: int = 20) -> str: ...

import sqlite3
from pathlib import Path

import httpx

from sensai.core.commands import CommandContext
from sensai.core.config import DEFAULT_CONFIG_PATH, GuardrailsConfig, load_config
from sensai.core.engine import ChatEngine
from sensai.domain.models import Conversation
from sensai.domain.protocols import Guardrail
from sensai.eval.guardrails import RegexGuardrail
from sensai.memory.rag.retriever import RAGRetriever
from sensai.memory.rag.store import SQLiteVectorStore
from sensai.memory.session import SqliteMemoryStore
from sensai.providers import get_provider
from sensai.providers.ollama import OllamaEmbeddingProvider
from sensai.tools.registry import build_default_registry


class BootstrapError(Exception):
    """Raised when optional session components cannot be initialized."""


def _build_guardrail(config: GuardrailsConfig) -> Guardrail | None:
    if not config.enabled:
        return None
    return RegexGuardrail(injection_action=config.injection, pii_action=config.pii)


async def build_session(
    *,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    interface: str | None = None,
    provider_name: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    session_name: str | None = None,
    rag_dir: str | None = None,
    rag_db: str = "rag.db",
    rag_model: str = "nomic-embed-text",
) -> CommandContext:
    """Resolve settings and construct the provider, memory, tools, and engine."""
    config = load_config(
        config_path,
        interface=interface,
        provider=provider_name,
        model=model,
        base_url=base_url,
    )
    provider = get_provider(
        config.provider, base_url=config.base_url, model=config.model
    )

    memory_store = SqliteMemoryStore()
    conversation = (
        await memory_store.load(session_name) if session_name is not None else None
    )
    if conversation is None:
        conversation = Conversation(id=session_name) if session_name else Conversation()

    tool_registry = build_default_registry(config.tools.fs_allowed_root)
    retriever = None
    if rag_dir is not None:
        try:
            retriever = RAGRetriever(
                OllamaEmbeddingProvider(base_url=config.base_url, model=rag_model),
                SQLiteVectorStore(db_path=rag_db),
            )
            await retriever.index_directory(rag_dir)
        except (
            OSError,
            sqlite3.Error,
            RuntimeError,
            ValueError,
            httpx.HTTPError,
        ) as exc:
            raise BootstrapError(f"RAG indexing failed: {exc}") from exc

    engine = ChatEngine(
        provider,
        conversation,
        tool_registry,
        retriever,
        _build_guardrail(config.guardrails),
    )
    return CommandContext(
        config=config,
        engine=engine,
        provider_factory=get_provider,
        tool_registry=tool_registry,
        tool_registry_factory=build_default_registry,
        memory_store=memory_store,
        config_path=Path(config_path),
    )

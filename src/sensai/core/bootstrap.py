import asyncio
import sqlite3
from functools import partial
from pathlib import Path

import httpx

from sensai.core.budget import ContextBudget, LLMSummarizer
from sensai.core.commands import CommandContext
from sensai.core.config import (
    DEFAULT_CONFIG_PATH,
    GuardrailsConfig,
    McpConfig,
    McpServerConfig,
    load_config,
)
from sensai.core.engine import ChatEngine
from sensai.domain.models import Conversation
from sensai.domain.protocols import Guardrail
from sensai.eval.guardrails import RegexGuardrail
from sensai.eval.logger import PromptLogger, ReplyLogger
from sensai.memory.manager import SqliteMemoryManager
from sensai.memory.rag.chunker import TextChunker
from sensai.memory.rag.retriever import RAGRetriever
from sensai.memory.rag.store import SQLiteVectorStore
from sensai.memory.session import SqliteMemoryStore
from sensai.providers import get_provider
from sensai.providers.ollama import OllamaEmbeddingProvider
from sensai.tools.mcp import McpClient, McpError, McpTool
from sensai.tools.registry import build_default_registry


class BootstrapError(Exception):
    """Raised when optional session components cannot be initialized."""


def _build_guardrail(config: GuardrailsConfig) -> Guardrail | None:
    if not config.enabled:
        return None
    return RegexGuardrail(injection_action=config.injection, pii_action=config.pii)


async def _start_mcp_server(
    name: str, server: McpServerConfig
) -> tuple[McpClient, list[McpTool]] | str:
    """Start one server and list its tools; a warning string if it cannot."""
    client = McpClient(server.command, server.args, server.env, server.timeout)
    try:
        await client.start()
        definitions = await client.list_tools()
    except McpError as exc:
        await client.close()
        return f"MCP server '{name}' skipped: {exc}"
    return client, [McpTool(client, name, definition) for definition in definitions]


async def _start_mcp_servers(
    config: McpConfig,
) -> tuple[list[McpClient], list[McpTool], list[str]]:
    """Start every configured server at once. A failing one is skipped with a warning."""
    outcomes = await asyncio.gather(
        *(_start_mcp_server(name, server) for name, server in config.servers.items())
    )
    clients: list[McpClient] = []
    tools: list[McpTool] = []
    warnings: list[str] = []
    for outcome in outcomes:
        if isinstance(outcome, str):
            warnings.append(outcome)
        else:
            clients.append(outcome[0])
            tools.extend(outcome[1])
    return clients, tools, warnings


async def build_session(
    *,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    interface: str | None = None,
    provider_name: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    session_name: str | None = None,
    rag_dir: str | None = None,
    rag_db: str | None = None,
    rag_model: str | None = None,
) -> CommandContext:
    """Resolve settings and construct the provider, memory, tools, and engine.

    The `rag_*` arguments (CLI flags) override `[rag]`; `rag_dir` also enables it.
    """
    config = load_config(
        config_path,
        interface=interface,
        provider=provider_name,
        model=model,
        base_url=base_url,
    )
    if rag_dir is not None:
        config.rag.enabled = True
        config.rag.dir = rag_dir
    if rag_db is not None:
        config.rag.db = rag_db
    if rag_model is not None:
        config.rag.model = rag_model
    rag = config.rag
    provider = get_provider(
        config.provider,
        base_url=config.base_url,
        model=config.model,
        api_key=config.api_key,
        options=config.options,
    )

    memory_store = SqliteMemoryStore()
    conversation = (
        await memory_store.load(session_name) if session_name is not None else None
    )
    if conversation is None:
        conversation = Conversation(id=session_name) if session_name else Conversation()

    retriever = None
    if rag.enabled and rag.dir is not None:
        try:
            retriever = RAGRetriever(
                OllamaEmbeddingProvider(base_url=config.base_url, model=rag.model),
                SQLiteVectorStore(db_path=rag.db),
                top_k=rag.top_k,
            )
            await retriever.index_directory(
                rag.dir, TextChunker(rag.chunk_size, rag.chunk_overlap)
            )
        except (
            OSError,
            sqlite3.Error,
            RuntimeError,
            ValueError,
            httpx.HTTPError,
        ) as exc:
            raise BootstrapError(f"RAG indexing failed: {exc}") from exc

    # Last step that can leave resources behind: servers started here are only
    # stopped by context.aclose(), so nothing after this may raise.
    mcp_clients, mcp_tools, warnings = await _start_mcp_servers(config.mcp)
    structured_memory = SqliteMemoryManager() if config.memory.enabled else None
    # The factory remembers the MCP tools so /config rebuilds keep them.
    registry_factory = partial(
        build_default_registry,
        extra_tools=mcp_tools,
        memory=structured_memory,
        web_search=config.tools.web_search,
        sandbox=config.tools.sandbox,
    )
    tool_registry = registry_factory(config.tools.fs_allowed_root)

    engine = ChatEngine(
        provider,
        conversation,
        tool_registry,
        retriever,
        guardrail=_build_guardrail(config.guardrails),
        recorder=(
            ReplyLogger(config.eval.replies_path) if config.eval.log_replies else None
        ),
        prompt_recorder=(
            PromptLogger(config.eval.prompts_path) if config.eval.log_prompts else None
        ),
        memory=structured_memory,
        memory_auto_inject=config.memory.auto_inject,
        reasoning=config.reasoning.enabled,
        split_thoughts=config.reasoning.show_thoughts,
        max_steps=config.reasoning.max_steps,
        think=config.reasoning.think,
    )
    engine.budget = ContextBudget(config.budget, LLMSummarizer(lambda: engine.provider))
    return CommandContext(
        config=config,
        engine=engine,
        provider_factory=get_provider,
        tool_registry=tool_registry,
        tool_registry_factory=registry_factory,
        memory_store=memory_store,
        structured_memory=structured_memory,
        config_path=Path(config_path),
        startup_warnings=warnings,
        closers=[client.close for client in mcp_clients],
    )

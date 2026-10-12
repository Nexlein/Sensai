import sys
from pathlib import Path

import pytest

from sensai.core.bootstrap import BootstrapError, build_session
from sensai.domain.events import GuardrailEvent
from sensai.domain.models import Conversation
from sensai.eval.guardrails import RegexGuardrail
from sensai.eval.judge.__main__ import load_items
from sensai.eval.logger import ReplyLogger
from sensai.memory.rag.store import SQLiteVectorStore


async def test_build_session_loads_config_tools_and_existing_session(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sensai.toml"
    config_path.write_text(
        f'provider = "mock"\n[tools]\nfs_allowed_root = "{tmp_path}"\n',
        encoding="utf-8",
    )

    first = await build_session(config_path=config_path, session_name="saved")
    first.engine.conversation.add_message("user", "previous question")
    await first.memory_store.save(first.engine.conversation)

    resumed = await build_session(config_path=config_path, session_name="saved")

    assert resumed.config.provider == "mock"
    assert resumed.config_path == config_path
    assert resumed.engine.conversation.id == "saved"
    assert resumed.engine.conversation.messages[0].content == "previous question"
    assert resumed.engine.registry is resumed.tool_registry
    assert resumed.structured_memory is not None
    assert resumed.tool_registry.get("read_file") is not None
    assert resumed.tool_registry.get("list_dir") is not None
    assert resumed.tool_registry.get("remember_fact") is not None
    assert resumed.tool_registry.get("recall_memory") is not None
    assert resumed.tool_registry.get("forget_fact") is not None
    assert resumed.tool_registry_factory(None).get("web_search") is not None
    assert resumed.tool_registry_factory(None).get("remember_fact") is not None


def _mcp_config(tmp_path, *, working="demo", broken=None):
    server = Path(__file__).parents[1] / "tools" / "mcp_test_server.py"
    text = f'provider = "mock"\n[tools]\nfs_allowed_root = "{tmp_path}"\n'
    if working:
        text += (
            f'[mcp.servers.{working}]\ncommand = "{sys.executable}"\n'
            f'args = ["{server}"]\n'
        )
    if broken:
        text += f'[mcp.servers.{broken}]\ncommand = "no-such-sensai-command"\n'
    config_path = tmp_path / "sensai.toml"
    config_path.write_text(text, encoding="utf-8")
    return config_path


async def test_build_session_registers_mcp_tools_behind_confirmation(tmp_path):
    context = await build_session(config_path=_mcp_config(tmp_path))
    try:
        tool = context.tool_registry.get("demo__add")

        assert tool is not None
        assert tool.requires_confirmation is True
        assert await tool.execute(a=1, b=2) == "3"
        assert context.startup_warnings == []
    finally:
        await context.aclose()


async def test_mcp_tools_survive_a_registry_rebuild(tmp_path):
    context = await build_session(config_path=_mcp_config(tmp_path))
    try:
        rebuilt = context.tool_registry_factory(None)

        assert rebuilt.get("demo__add") is not None
        assert rebuilt.get("read_file") is None
    finally:
        await context.aclose()


async def test_failing_mcp_server_is_skipped_with_a_warning(tmp_path):
    context = await build_session(config_path=_mcp_config(tmp_path, broken="bad"))
    try:
        assert context.tool_registry.get("demo__add") is not None
        assert len(context.startup_warnings) == 1
        assert "MCP server 'bad' skipped" in context.startup_warnings[0]
    finally:
        await context.aclose()


async def test_session_starts_when_every_mcp_server_fails(tmp_path):
    config_path = _mcp_config(tmp_path, working=None, broken="bad")

    context = await build_session(config_path=config_path)

    assert context.tool_registry.get("read_file") is not None
    assert len(context.startup_warnings) == 1


async def test_aclose_stops_the_mcp_servers(tmp_path):
    context = await build_session(config_path=_mcp_config(tmp_path))
    tool = context.tool_registry.get("demo__add")

    await context.aclose()

    assert await tool.execute(a=1, b=2) == "Error: MCP server is not running"


async def test_build_session_indexes_rag_documents(monkeypatch, tmp_path):
    class FakeEmbeddingProvider:
        def __init__(self, base_url: str, model: str):
            self.base_url = base_url
            self.model = model

        async def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sensai.core.bootstrap.OllamaEmbeddingProvider", FakeEmbeddingProvider
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("project guide", encoding="utf-8")

    context = await build_session(
        provider_name="mock",
        rag_dir=str(docs),
        rag_db=str(tmp_path / "rag.db"),
    )

    assert context.engine.retriever is not None
    assert "project guide" in await context.engine.retriever.retrieve_context("query")
    assert SQLiteVectorStore(str(tmp_path / "rag.db")).search([1.0, 0.0])
    assert isinstance(context.engine.conversation, Conversation)


async def test_build_session_reports_rag_failure(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(BootstrapError, match="RAG indexing failed"):
        await build_session(
            provider_name="mock",
            rag_dir=str(tmp_path / "missing"),
            rag_db=str(tmp_path / "rag.db"),
        )


async def test_build_session_uses_interface_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sensai.toml"
    config_path.write_text('interface = "tui"\nprovider = "mock"\n')

    context = await build_session(config_path=config_path, interface="cli")

    assert context.config.interface == "cli"


async def test_build_session_wires_budget_from_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sensai.toml"
    config_path.write_text('provider = "mock"\n[budget]\nmax_tokens = 512\n')

    context = await build_session(config_path=config_path)

    assert context.engine.budget is not None
    assert context.engine.budget.config.max_tokens == 512


async def test_budget_summarizer_follows_provider_swap(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    context = await build_session(provider_name="mock")
    swapped = object()

    context.engine.provider = swapped

    assert context.engine.budget.summarizer.get_provider() is swapped


async def test_build_session_has_a_guardrail_by_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    context = await build_session(provider_name="mock")

    guardrail = context.engine.guardrail
    assert isinstance(guardrail, RegexGuardrail)
    assert guardrail.injection_action == "block"
    assert guardrail.pii_action == "redact"


async def test_build_session_has_no_guardrail_when_disabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sensai.toml"
    config_path.write_text('provider = "mock"\n[guardrails]\nenabled = false\n')

    context = await build_session(config_path=config_path)

    assert context.engine.guardrail is None


async def test_build_session_records_no_replies_by_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    context = await build_session(provider_name="mock")

    assert context.engine.recorder is None


async def test_build_session_logs_replies_when_enabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    replies = tmp_path / "out" / "replies.jsonl"
    config_path = tmp_path / "sensai.toml"
    config_path.write_text(
        f'provider = "mock"\n[eval]\nlog_replies = true\nreplies_path = "{replies}"\n'
    )

    context = await build_session(config_path=config_path)
    _ = [e async for e in context.engine.send("hello")]

    assert isinstance(context.engine.recorder, ReplyLogger)
    assert [item.question for item in load_items(replies)] == ["hello"]


async def test_build_session_builds_guardrail_from_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sensai.toml"
    config_path.write_text(
        'provider = "mock"\n'
        '[guardrails]\nenabled = true\ninjection = "flag"\npii = "block"\n'
    )

    context = await build_session(config_path=config_path)

    guardrail = context.engine.guardrail
    assert isinstance(guardrail, RegexGuardrail)
    assert guardrail.injection_action == "flag"
    assert guardrail.pii_action == "block"


async def test_enabled_guardrail_protects_a_real_session_turn(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sensai.toml"
    config_path.write_text('provider = "mock"\n[guardrails]\nenabled = true\n')
    context = await build_session(config_path=config_path)

    events = [e async for e in context.engine.send("my mail is a@b.io")]

    assert [e.action for e in events if isinstance(e, GuardrailEvent)] == ["redact"]
    assert context.engine.conversation.messages[0].content == "my mail is [EMAIL]"

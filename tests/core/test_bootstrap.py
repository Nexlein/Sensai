import pytest

from sensai.core.bootstrap import BootstrapError, build_session
from sensai.domain.models import Conversation
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
    assert resumed.tool_registry.get("read_file") is not None
    assert resumed.tool_registry.get("list_dir") is not None
    assert resumed.tool_registry_factory(None).get_tools_schema() == []


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

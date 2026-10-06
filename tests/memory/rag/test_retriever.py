import os

import pytest

from sensai.domain.models import Chunk, generate_uuid
from sensai.memory.rag.retriever import RAGRetriever
from sensai.memory.rag.store import SQLiteVectorStore


class MockProvider:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        # Mock embedding: just return [1.0, 0.0] for simplicity
        return [[1.0, 0.0] for _ in texts]


@pytest.mark.asyncio
async def test_retrieve_context():
    db_path = "test_retriever.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    store = SQLiteVectorStore(db_path=db_path)
    store.save_chunks(
        [
            Chunk(
                id=generate_uuid(),
                doc_id="d1",
                text="test chunk",
                embedding=[1.0, 0.0],
                metadata={"filename": "doc.md"},
            )
        ]
    )

    provider = MockProvider()
    retriever = RAGRetriever(provider=provider, store=store)  # type: ignore

    context = await retriever.retrieve_context("query")
    assert "--- Source: doc.md ---" in context
    assert "test chunk" in context

    os.remove(db_path)


class KeywordEmbeddingProvider:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "apple" in text else [0.0, 1.0] for text in texts]


async def test_index_directory_embeds_and_replaces_stale_documents(tmp_path):
    from sensai.memory.rag.chunker import TextChunker

    docs = tmp_path / "docs"
    docs.mkdir()
    apple = docs / "apple.md"
    apple.write_text("apple facts", encoding="utf-8")
    (docs / "banana.txt").write_text("banana facts", encoding="utf-8")

    store = SQLiteVectorStore(str(tmp_path / "rag.db"))
    retriever = RAGRetriever(KeywordEmbeddingProvider(), store)
    assert await retriever.index_directory(str(docs), TextChunker(chunk_size=100)) == 2
    assert "apple facts" in await retriever.retrieve_context("apple question", top_k=1)

    apple.unlink()
    assert await retriever.index_directory(str(docs), TextChunker(chunk_size=100)) == 1
    assert "apple facts" not in await retriever.retrieve_context("apple question")


async def test_index_directory_keeps_old_index_when_embeddings_fail(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "one.md").write_text("one", encoding="utf-8")

    store = SQLiteVectorStore(str(tmp_path / "rag.db"))
    store.save_chunks([Chunk(id="old", doc_id="old", text="old", embedding=[1.0, 0.0])])

    class ShortProvider:
        async def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return []

    retriever = RAGRetriever(ShortProvider(), store)
    with pytest.raises(ValueError, match="number of vectors"):
        await retriever.index_directory(str(docs))

    assert [chunk.text for chunk in store.search([1.0, 0.0])] == ["old"]


async def test_indexed_document_reaches_chat_prompt(tmp_path):
    from sensai.core.engine import ChatEngine
    from sensai.domain.events import TextChunkEvent
    from sensai.domain.models import Conversation

    class RecordingProvider:
        def __init__(self):
            self.prompt = None

        async def chat_stream(self, messages, tools=None):
            self.prompt = messages
            yield TextChunkEvent(content="answer")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "facts.md").write_text("apple facts", encoding="utf-8")
    retriever = RAGRetriever(
        KeywordEmbeddingProvider(), SQLiteVectorStore(str(tmp_path / "rag.db"))
    )
    await retriever.index_directory(str(docs))

    provider = RecordingProvider()
    engine = ChatEngine(provider, Conversation(), retriever=retriever)
    _ = [event async for event in engine.send("apple question")]

    assert provider.prompt is not None
    assert "apple facts" in provider.prompt[0].content
    assert provider.prompt[-1].content == "apple question"

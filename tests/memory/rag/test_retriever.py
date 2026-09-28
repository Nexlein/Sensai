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

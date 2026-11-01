"""RAG vector store (SQLite, cosine)."""

import os

from sensai.domain.models import Chunk, generate_uuid
from sensai.memory.rag.store import SQLiteVectorStore, cosine_similarity


def test_cosine_similarity():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_store_save_search():
    db_path = "test_rag.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    store = SQLiteVectorStore(db_path=db_path)
    c1 = Chunk(id=generate_uuid(), doc_id="d1", text="hello", embedding=[1.0, 0.0])
    c2 = Chunk(id=generate_uuid(), doc_id="d2", text="world", embedding=[0.0, 1.0])

    store.save_chunks([c1, c2])

    results = store.search([1.0, 0.0], top_k=1)
    assert len(results) == 1
    assert results[0].text == "hello"
    assert results[0].score == 1.0

    os.remove(db_path)


def test_store_rejects_unembedded_chunks_and_preserves_previous_index(tmp_path):
    import pytest

    store = SQLiteVectorStore(str(tmp_path / "rag.db"))
    good = Chunk(id="good", doc_id="d1", text="good", embedding=[1.0, 0.0])
    store.replace_chunks([good])

    with pytest.raises(ValueError, match="embedding"):
        store.replace_chunks([Chunk(id="bad", doc_id="d2", text="bad")])

    assert [chunk.text for chunk in store.search([1.0, 0.0])] == ["good"]


def test_search_rejects_embedding_dimension_mismatch(tmp_path):
    import pytest

    store = SQLiteVectorStore(str(tmp_path / "rag.db"))
    store.save_chunks([Chunk(id="c", doc_id="d", text="text", embedding=[1.0, 0.0])])

    with pytest.raises(ValueError, match="dimensions"):
        store.search([1.0, 0.0, 0.0])


def test_store_closes_every_connection_it_opens(tmp_path, opened_connections):
    import sqlite3

    import pytest

    store = SQLiteVectorStore(str(tmp_path / "rag.db"))
    good = Chunk(id="good", doc_id="d1", text="good", embedding=[1.0, 0.0])
    store.save_chunks([good])
    store.replace_chunks([good])
    store.search([1.0, 0.0])
    with pytest.raises(ValueError, match="embedding"):
        store.replace_chunks([Chunk(id="bad", doc_id="d2", text="bad")])

    assert len(opened_connections) == 5
    for conn in opened_connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


def test_search_rejects_non_positive_top_k(tmp_path):
    import pytest

    store = SQLiteVectorStore(str(tmp_path / "rag.db"))

    with pytest.raises(ValueError, match="top_k must be positive"):
        store.search([1.0, 0.0], top_k=0)


def test_vectors_are_stored_packed_and_read_back_exactly(tmp_path):
    import sqlite3

    store = SQLiteVectorStore(str(tmp_path / "rag.db"))
    vector = [0.1, -0.25, 3.0]
    store.save_chunks([Chunk(id="c", doc_id="d", text="t", embedding=vector)])

    with sqlite3.connect(tmp_path / "rag.db") as conn:
        raw = conn.execute("SELECT embedding FROM chunks").fetchone()[0]

    assert isinstance(raw, bytes)
    assert store.search(vector, top_k=1)[0].embedding == vector


def test_indexes_written_as_json_are_still_searchable(tmp_path):
    import json
    import sqlite3

    store = SQLiteVectorStore(str(tmp_path / "rag.db"))
    with sqlite3.connect(tmp_path / "rag.db") as conn:
        conn.execute(
            "INSERT INTO chunks VALUES (?, ?, ?, ?, ?)",
            ("old", "d", "legacy", "{}", json.dumps([0.0, 1.0])),
        )

    assert store.search([0.0, 1.0])[0].text == "legacy"


def test_search_keeps_the_best_chunks_in_score_order(tmp_path):
    store = SQLiteVectorStore(str(tmp_path / "rag.db"))
    store.save_chunks(
        [
            Chunk(id=str(i), doc_id="d", text=str(i), embedding=[1.0, float(i)])
            for i in range(10)
        ]
    )

    results = store.search([1.0, 0.0], top_k=3)

    assert [chunk.text for chunk in results] == ["0", "1", "2"]
    assert results[0].score > results[1].score > results[2].score

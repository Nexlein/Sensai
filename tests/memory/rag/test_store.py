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

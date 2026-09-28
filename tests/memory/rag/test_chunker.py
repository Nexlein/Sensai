import os
import tempfile

from sensai.memory.rag.chunker import TextChunker


def test_ingest_directory():
    chunker = TextChunker()
    with tempfile.TemporaryDirectory() as temp_dir:
        with open(os.path.join(temp_dir, "test.md"), "w") as f:
            f.write("test content")
        docs = chunker.ingest_directory(temp_dir)
        assert len(docs) == 1
        assert docs[0].content == "test content"
        assert docs[0].metadata["filename"] == "test.md"


def test_chunk_documents():
    chunker = TextChunker(chunk_size=10, chunk_overlap=2)
    with tempfile.TemporaryDirectory() as temp_dir:
        with open(os.path.join(temp_dir, "test.md"), "w") as f:
            f.write("0123456789abcdefghij")
        docs = chunker.ingest_directory(temp_dir)
        chunks = chunker.chunk_documents(docs)
        assert len(chunks) == 3
        assert chunks[0].text == "0123456789"
        assert chunks[1].text == "89abcdefgh"
        assert chunks[2].text == "ghij"


def test_chunker_rejects_non_positive_stride():
    import pytest

    for size, overlap in [(0, 0), (10, 10), (10, 11), (10, -1)]:
        with pytest.raises(ValueError):
            TextChunker(chunk_size=size, chunk_overlap=overlap)


def test_exactly_one_chunk_has_no_overlap_only_tail(tmp_path):
    from sensai.domain.models import Document

    chunker = TextChunker(chunk_size=10, chunk_overlap=2)
    doc = Document(path="one.md", content="0123456789")
    chunks = chunker.chunk_documents([doc])

    assert [chunk.text for chunk in chunks] == ["0123456789"]


def test_missing_directory_is_an_error(tmp_path):
    import pytest

    with pytest.raises(NotADirectoryError):
        TextChunker().ingest_directory(str(tmp_path / "missing"))

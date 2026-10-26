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


def test_ingest_keeps_only_text_and_markdown_files(tmp_path):
    (tmp_path / "notes.md").write_text("md", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("txt", encoding="utf-8")
    (tmp_path / "script.py").write_text("print()", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")

    docs = TextChunker().ingest_directory(str(tmp_path))

    assert sorted(doc.metadata["filename"] for doc in docs) == ["notes.md", "notes.txt"]


def test_ingest_skips_symlink_pointing_outside_the_directory(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    secret = tmp_path / "secret.md"
    secret.write_text("outside the corpus", encoding="utf-8")
    try:
        os.symlink(secret, corpus / "leak.md")
    except OSError:
        import pytest

        pytest.skip("symlinks not supported here")

    docs = TextChunker().ingest_directory(str(corpus))

    assert docs == []


def test_ingest_skips_files_that_are_not_utf8(tmp_path):
    (tmp_path / "latin1.txt").write_bytes("caf\xe9".encode("latin-1"))
    (tmp_path / "ok.md").write_text("ok", encoding="utf-8")

    docs = TextChunker().ingest_directory(str(tmp_path))

    assert [doc.content for doc in docs] == ["ok"]

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

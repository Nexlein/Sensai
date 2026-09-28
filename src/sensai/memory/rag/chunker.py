import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sensai.domain.models import Chunk, Document


class TextChunker:
    """Ingest local text documents and split them into overlapping chunks."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError(
                "chunk_size must be positive and chunk_overlap must be in [0, chunk_size)"
            )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def ingest_directory(self, path: str) -> list[Document]:
        """Read .txt and .md files within a directory."""
        directory = Path(path).resolve()
        if not directory.is_dir():
            raise NotADirectoryError(f"RAG directory does not exist: {path}")

        docs = []
        for root, _, files in os.walk(directory):
            for filename in sorted(files):
                if not filename.endswith((".txt", ".md")):
                    continue
                file_path = Path(root, filename)
                try:
                    resolved_path = file_path.resolve()
                    if not resolved_path.is_relative_to(directory):
                        continue
                    content = file_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                docs.append(
                    Document(
                        id=str(uuid5(NAMESPACE_URL, str(resolved_path))),
                        path=str(resolved_path),
                        content=content,
                        metadata={"filename": filename, "path": str(resolved_path)},
                    )
                )
        return docs

    def chunk_documents(self, documents: list[Document]) -> list[Chunk]:
        """Split documents without emitting an overlap-only trailing chunk."""
        chunks = []
        for doc in documents:
            text = doc.content
            start = 0
            while start < len(text):
                end = start + self.chunk_size
                chunks.append(
                    Chunk(
                        id=str(uuid5(NAMESPACE_URL, f"{doc.id}:{start}")),
                        doc_id=doc.id,
                        text=text[start:end],
                        metadata=doc.metadata.copy(),
                    )
                )
                if end >= len(text):
                    break
                start += self.chunk_size - self.chunk_overlap
        return chunks

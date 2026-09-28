import os

from sensai.domain.models import Chunk, Document, generate_uuid


class TextChunker:
    """Utility to ingest documents and split them into smaller chunks."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def ingest_directory(self, path: str) -> list[Document]:
        """Walk a directory and ingest all .txt and .md files."""
        docs = []
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith((".txt", ".md")):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        docs.append(
                            Document(
                                id=generate_uuid(),
                                path=file_path,
                                content=content,
                                metadata={"filename": file},
                            )
                        )
                    except (OSError, UnicodeDecodeError):
                        continue
        return docs

    def chunk_documents(self, documents: list[Document]) -> list[Chunk]:
        """Split a list of Documents into a list of Chunks."""
        chunks = []
        for doc in documents:
            text = doc.content
            if not text:
                continue

            start = 0
            while start < len(text):
                end = start + self.chunk_size
                chunk_text = text[start:end]
                chunks.append(
                    Chunk(
                        id=generate_uuid(),
                        doc_id=doc.id,
                        text=chunk_text,
                        metadata=doc.metadata.copy(),
                    )
                )
                start += self.chunk_size - self.chunk_overlap
        return chunks

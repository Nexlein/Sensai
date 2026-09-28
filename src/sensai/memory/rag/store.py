import json
import math
import sqlite3

from sensai.domain.models import Chunk, ScoredChunk


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate the cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class SQLiteVectorStore:
    """A local vector store using SQLite for persistence."""

    def __init__(self, db_path: str = "rag.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT,
                    text TEXT,
                    metadata TEXT,
                    embedding TEXT
                )
                """
            )

    def save_chunks(self, chunks: list[Chunk]):
        """Save a list of Chunks to the SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            for chunk in chunks:
                emb = json.dumps(chunk.embedding) if chunk.embedding else None
                meta = json.dumps(chunk.metadata)
                conn.execute(
                    "INSERT OR REPLACE INTO chunks (id, doc_id, text, metadata, embedding) VALUES (?, ?, ?, ?, ?)",
                    (chunk.id, chunk.doc_id, chunk.text, meta, emb),
                )

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[ScoredChunk]:
        """Search for the top K most similar chunks using cosine similarity."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, doc_id, text, metadata, embedding FROM chunks"
            )
            rows = cursor.fetchall()

        results = []
        for row in rows:
            cid, doc_id, text, meta_str, emb_str = row
            if not emb_str:
                continue
            emb = json.loads(emb_str)
            score = cosine_similarity(query_embedding, emb)
            meta = json.loads(meta_str) if meta_str else {}
            results.append(
                ScoredChunk(
                    id=cid,
                    doc_id=doc_id,
                    text=text,
                    metadata=meta,
                    embedding=emb,
                    score=score,
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

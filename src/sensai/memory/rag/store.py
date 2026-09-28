import json
import math
import sqlite3

from sensai.domain.models import Chunk, ScoredChunk


def _validate_embedding(embedding: list[float] | None) -> list[float]:
    if not embedding or not all(math.isfinite(value) for value in embedding):
        raise ValueError("Every stored chunk needs a non-empty, finite embedding")
    return embedding


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate cosine similarity only for compatible vectors."""
    _validate_embedding(v1)
    _validate_embedding(v2)
    if len(v1) != len(v2):
        raise ValueError("Embedding dimensions do not match")
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class SQLiteVectorStore:
    """Persist document chunks and search them by cosine similarity."""

    def __init__(self, db_path: str = "rag.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
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

    @staticmethod
    def _insert_chunks(conn: sqlite3.Connection, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            conn.execute(
                "INSERT OR REPLACE INTO chunks (id, doc_id, text, metadata, embedding) VALUES (?, ?, ?, ?, ?)",
                (
                    chunk.id,
                    chunk.doc_id,
                    chunk.text,
                    json.dumps(chunk.metadata),
                    json.dumps(_validate_embedding(chunk.embedding)),
                ),
            )

    def save_chunks(self, chunks: list[Chunk]) -> None:
        """Add or update already embedded chunks."""
        with sqlite3.connect(self.db_path) as conn:
            self._insert_chunks(conn, chunks)

    def replace_chunks(self, chunks: list[Chunk]) -> None:
        """Atomically replace an index, including stale or deleted documents."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM chunks")
            self._insert_chunks(conn, chunks)

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[ScoredChunk]:
        """Return the top K chunks for a compatible query embedding."""
        _validate_embedding(query_embedding)
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, doc_id, text, metadata, embedding FROM chunks"
            ).fetchall()

        results = []
        for cid, doc_id, text, meta_str, emb_str in rows:
            if not emb_str:
                continue
            embedding = json.loads(emb_str)
            results.append(
                ScoredChunk(
                    id=cid,
                    doc_id=doc_id,
                    text=text,
                    metadata=json.loads(meta_str) if meta_str else {},
                    embedding=embedding,
                    score=cosine_similarity(query_embedding, embedding),
                )
            )

        results.sort(key=lambda chunk: chunk.score, reverse=True)
        return results[:top_k]

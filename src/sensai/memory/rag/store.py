import heapq
import json
import math
import operator
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager


from array import array

from sensai.domain.models import Chunk, ScoredChunk


def _validate_embedding(embedding: list[float] | None) -> list[float]:
    if not embedding or not all(math.isfinite(value) for value in embedding):
        raise ValueError("Every stored chunk needs a non-empty, finite embedding")
    return embedding


def _dot(v1: "list[float] | array[float]", v2: "list[float] | array[float]") -> float:
    """Dot product in C when the interpreter has `math.sumprod` (3.12+)."""
    sumprod = getattr(math, "sumprod", None)
    if sumprod is not None:
        return sumprod(v1, v2)
    return sum(map(operator.mul, v1, v2))


def _decode(raw: bytes | str) -> "array[float]":
    """A stored embedding: packed doubles, or JSON from indexes built before."""
    if isinstance(raw, bytes):
        vector = array("d")
        vector.frombytes(raw)
        return vector
    return array("d", json.loads(raw))


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

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection that commits on success, rolls back on error, then closes."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            yield conn

    def _init_db(self) -> None:
        with self._connect() as conn:
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
                    array("d", _validate_embedding(chunk.embedding)).tobytes(),
                ),
            )

    def save_chunks(self, chunks: list[Chunk]) -> None:
        """Add or update already embedded chunks."""
        with self._connect() as conn:
            self._insert_chunks(conn, chunks)

    def replace_chunks(self, chunks: list[Chunk]) -> None:
        """Atomically replace an index, including stale or deleted documents."""
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks")
            self._insert_chunks(conn, chunks)

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[ScoredChunk]:
        """Return the top K chunks for a compatible query embedding.

        Vectors are read as packed doubles and scored with a C dot product; only
        the K best rows become `ScoredChunk` objects.
        """
        query = _validate_embedding(query_embedding)
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, doc_id, text, metadata, embedding FROM chunks"
            ).fetchall()

        query_norm = math.sqrt(_dot(query, query))
        scored = []
        for row in rows:
            if not row[4]:
                continue
            vector = _decode(row[4])
            if len(vector) != len(query):
                raise ValueError("Embedding dimensions do not match")
            norm = math.sqrt(_dot(vector, vector))
            score = (
                _dot(query, vector) / (query_norm * norm)
                if query_norm and norm
                else 0.0
            )
            scored.append((score, row, vector))

        return [
            ScoredChunk(
                id=cid,
                doc_id=doc_id,
                text=text,
                metadata=json.loads(meta_str) if meta_str else {},
                embedding=list(vector),
                score=score,
            )
            for score, (cid, doc_id, text, meta_str, _), vector in heapq.nlargest(
                top_k, scored, key=operator.itemgetter(0)
            )
        ]

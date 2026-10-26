import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sensai.domain.models import Fact
from sensai.domain.protocols import StructuredMemory
from sensai.memory.db import DEFAULT_DB_PATH, connect, transaction

_WORD = re.compile(r"[^\W_]+")


def _words(text: str) -> list[str]:
    """Casefolded words of `text` without accents; `_` splits words too."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return _WORD.findall("".join(c for c in decomposed if not unicodedata.combining(c)))


class SqliteMemoryManager(StructuredMemory):
    """SQLite-backed structured memory manager (M3) for facts and entities."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path
        connect(db_path).close()

    def store_fact(
        self,
        entity: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        tags: list[str] | None = None,
        entity_type: str = "generic",
    ) -> Fact:
        entity = entity.strip()
        key = key.strip()
        value = value.strip()
        if not entity:
            raise ValueError("entity name must not be blank")
        if not key:
            raise ValueError("fact key must not be blank")
        if not value:
            raise ValueError("fact value must not be blank")

        tags_list = [t.strip() for t in (tags or []) if t.strip()]
        tags_json = json.dumps(tags_list)
        now_str = datetime.now(UTC).isoformat()
        fact_id = str(uuid4())

        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO entities (id, name, entity_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (str(uuid4()), entity, entity_type, now_str, now_str),
            )
            conn.execute(
                """
                INSERT INTO facts (id, entity_name, key, value, confidence, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_name, key) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    tags = excluded.tags,
                    updated_at = excluded.updated_at
                """,
                (
                    fact_id,
                    entity,
                    key,
                    value,
                    confidence,
                    tags_json,
                    now_str,
                    now_str,
                ),
            )

        fact = self.get_fact(entity, key)
        if fact is None:
            raise RuntimeError(f"Failed to retrieve stored fact for {entity}.{key}")
        return fact

    def get_fact(self, entity: str, key: str) -> Fact | None:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT id, entity_name, key, value, confidence, tags, created_at, updated_at
                FROM facts
                WHERE entity_name = ? AND key = ?
                """,
                (entity.strip(), key.strip()),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_fact(row)

    def list_facts(
        self, entity: str | None = None, tag: str | None = None
    ) -> list[Fact]:
        query = (
            "SELECT id, entity_name, key, value, confidence, tags, created_at, updated_at "
            "FROM facts WHERE 1=1"
        )
        params: list[str] = []
        if entity is not None and entity.strip():
            query += " AND entity_name = ?"
            params.append(entity.strip())

        query += " ORDER BY entity_name ASC, key ASC"
        with transaction(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        facts = [self._row_to_fact(r) for r in rows]

        if tag is not None and tag.strip():
            tag_clean = tag.strip().lower()
            facts = [f for f in facts if any(t.lower() == tag_clean for t in f.tags)]
        return facts

    def search_facts(self, query: str) -> list[Fact]:
        """Facts whose entity, key or value has a word starting with a query word.

        Accents, case and `_` do not matter: "éditeur préféré" finds the key
        "editeur_prefere". Facts matching more words come first."""
        words = _words(query)
        # "de", "la", "my" would match half the facts; keep them only if alone.
        words = [w for w in words if len(w) > 2] or words
        if not words:
            return []
        ranked: list[tuple[int, Fact]] = []
        for fact in self.list_facts():
            fact_words = _words(f"{fact.entity_name} {fact.key} {fact.value}")
            hits = sum(any(fw.startswith(w) for fw in fact_words) for w in words)
            if hits:
                ranked.append((hits, fact))
        # Stable sort: equal ranks keep list_facts' entity, key order.
        ranked.sort(key=lambda item: -item[0])
        return [fact for _, fact in ranked]

    def delete_fact(self, entity: str, key: str) -> bool:
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM facts WHERE entity_name = ? AND key = ?",
                (entity.strip(), key.strip()),
            )
            return cursor.rowcount > 0

    def delete_entity(self, entity: str) -> bool:
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM entities WHERE name = ?", (entity.strip(),)
            )
            return cursor.rowcount > 0

    def clear(self) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM facts")
            conn.execute("DELETE FROM entities")

    def format_context(self, entity: str | None = None, max_facts: int = 20) -> str:
        facts = self.list_facts(entity=entity)[:max_facts]
        if not facts:
            return ""
        lines = [f"- {f.entity_name}.{f.key}: {f.value}" for f in facts]
        return "\n".join(lines)

    @staticmethod
    def _row_to_fact(
        row: tuple[str, str, str, str, float, str | None, str, str],
    ) -> Fact:
        (
            fact_id,
            entity_name,
            key,
            value,
            confidence,
            tags_raw,
            created_at,
            updated_at,
        ) = row
        tags = json.loads(tags_raw) if tags_raw else []
        return Fact(
            id=fact_id,
            entity_name=entity_name,
            key=key,
            value=value,
            confidence=float(confidence),
            tags=tags,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )

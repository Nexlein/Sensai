import json
from pathlib import Path

from sensai.domain.models import Conversation, Message, ToolCall
from sensai.memory.db import DEFAULT_DB_PATH, connect, transaction


class SqliteMemoryStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        connect(db_path).close()

    async def save(self, conversation: Conversation) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, created_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (
                    conversation.id,
                    conversation.created_at.isoformat(),
                    conversation.updated_at.isoformat(),
                ),
            )
            conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (conversation.id,)
            )
            conn.executemany(
                """
                INSERT INTO messages (id, conversation_id, role, content, tool_calls, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        msg.id,
                        conversation.id,
                        msg.role,
                        msg.content,
                        json.dumps([tc.model_dump() for tc in msg.tool_calls])
                        if msg.tool_calls is not None
                        else None,
                        msg.timestamp.isoformat(),
                    )
                    for msg in conversation.messages
                ],
            )

    async def load(self, conversation_id: str) -> Conversation | None:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return None

            message_rows = conn.execute(
                """
                SELECT id, role, content, tool_calls, timestamp
                FROM messages WHERE conversation_id = ?
                ORDER BY timestamp ASC
                """,
                (conversation_id,),
            ).fetchall()

        messages = [
            Message(
                id=msg_id,
                role=role,
                content=content,
                tool_calls=[ToolCall(**tc) for tc in json.loads(tool_calls)]
                if tool_calls is not None
                else None,
                timestamp=timestamp,
            )
            for msg_id, role, content, tool_calls, timestamp in message_rows
        ]

        conv_id, created_at, updated_at = row
        return Conversation(
            id=conv_id,
            messages=messages,
            created_at=created_at,
            updated_at=updated_at,
        )

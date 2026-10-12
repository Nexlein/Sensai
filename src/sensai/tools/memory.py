import sqlite3
from typing import Any

from sensai.domain.protocols import StructuredMemory
from sensai.tools.base import SensitiveTool, Tool


class RememberFactTool(Tool):
    name = "remember_fact"
    description = (
        "Store or update a structured fact about an entity in long-term memory across sessions. "
        "Use this to remember user preferences, project conventions, tech stack, or environment facts."
    )

    def __init__(self, memory: StructuredMemory) -> None:
        self.memory = memory
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity name, for example 'user', 'project', or 'environment'.",
                },
                "key": {
                    "type": "string",
                    "description": "The specific attribute or fact key, e.g. 'preferred_language', 'linter'.",
                },
                "value": {
                    "type": "string",
                    "description": "The value or details to remember.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional category tags, e.g. ['preference', 'tooling'].",
                },
            },
            "required": ["entity", "key", "value"],
        }

    async def execute(
        self,
        entity: str,
        key: str,
        value: str,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            fact = self.memory.store_fact(
                entity=entity, key=key, value=value, tags=tags
            )
            tags_str = f" [{', '.join(fact.tags)}]" if fact.tags else ""
            return f"Remembered: {fact.entity_name}.{fact.key} = {fact.value}{tags_str}"
        except (ValueError, sqlite3.Error, RuntimeError) as e:
            return f"Error storing memory: {e}"


class RecallMemoryTool(Tool):
    name = "recall_memory"
    description = "Search or retrieve stored facts from long-term memory about the user, project, or other entities."

    def __init__(self, memory: StructuredMemory) -> None:
        self.memory = memory
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword matching entity name, key, or value.",
                },
                "entity": {
                    "type": "string",
                    "description": "Optional entity name filter, e.g. 'user' or 'project'.",
                },
            },
        }

    async def execute(
        self,
        query: str | None = None,
        entity: str | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            if query and query.strip():
                facts = self.memory.search_facts(query.strip())
                if entity and entity.strip():
                    facts = [
                        f
                        for f in facts
                        if f.entity_name.lower() == entity.strip().lower()
                    ]
            elif entity and entity.strip():
                facts = self.memory.list_facts(entity=entity.strip())
            else:
                facts = self.memory.list_facts()

            if not facts:
                return "No matching memories found."

            lines = [f"- {f.entity_name}.{f.key}: {f.value}" for f in facts]
            return "\n".join(lines)
        except (ValueError, sqlite3.Error, RuntimeError) as e:
            return f"Error recalling memory: {e}"


class ForgetFactTool(SensitiveTool):
    name = "forget_fact"
    description = (
        "Delete a stored fact about an entity from long-term memory across sessions. "
        "The user must confirm this deletion."
    )

    def __init__(self, memory: StructuredMemory) -> None:
        self.memory = memory
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Name of the entity, e.g. 'user' or 'project'.",
                },
                "key": {
                    "type": "string",
                    "description": "The fact key to delete, e.g. 'preferred_language'.",
                },
            },
            "required": ["entity", "key"],
        }

    def preview(self, entity: str, key: str, **kwargs: Any) -> str | None:
        fact = self.memory.get_fact(entity, key)
        if fact is None:
            return f"Forget fact: {entity}.{key} (fact does not exist)"
        return f"Forget fact: {entity}.{key} = {fact.value}"

    async def execute(self, entity: str, key: str, **kwargs: Any) -> str:
        try:
            deleted = self.memory.delete_fact(entity, key)
            if deleted:
                return f"Successfully deleted memory: {entity}.{key}"
            return f"No memory found for {entity}.{key}"
        except (ValueError, sqlite3.Error, RuntimeError) as e:
            return f"Error forgetting memory: {e}"

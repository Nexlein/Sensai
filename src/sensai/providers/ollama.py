import json
from collections import deque
from collections.abc import AsyncGenerator
from typing import Any

from sensai.domain.events import Event, TextChunkEvent, ToolCallEvent
from sensai.domain.models import Message
from sensai.providers.base import BaseHTTPProvider


class OllamaLLMProvider(BaseHTTPProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3.5:4b",
        timeout: float = 60.0,
    ) -> None:
        super().__init__(base_url=base_url, timeout=timeout)
        self.model = model

    def _format_message(self, msg: Message) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            payload["tool_calls"] = [
                {"function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in msg.tool_calls
            ]
        return payload

    def _format_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Associate tool results with the preceding assistant tool calls."""
        formatted: list[dict[str, Any]] = []
        pending_tools: deque[str] = deque()
        for message in messages:
            payload = self._format_message(message)
            if message.role == "assistant":
                pending_tools = deque(tc.name for tc in message.tool_calls or [])
            elif message.role == "tool" and pending_tools:
                payload["tool_name"] = pending_tools.popleft()
            formatted.append(payload)
        return formatted

    def _parse_line(self, line: str) -> list[Event]:
        msg = json.loads(line).get("message", {})
        events: list[Event] = [
            ToolCallEvent(
                tool_name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments", {}),
            )
            for tc in msg.get("tool_calls") or []
        ]
        if content := msg.get("content"):
            events.append(TextChunkEvent(content=content))
        return events

    async def _stream_response(self, payload: dict[str, Any]) -> AsyncGenerator[Event]:
        async with (
            self._get_client() as client,
            client.stream("POST", "/api/chat", json=payload) as response,
        ):
            await self._check_response_status(response)
            async for line in response.aiter_lines():
                if stripped := line.strip():
                    for event in self._parse_line(stripped):
                        yield event

    async def chat_stream(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[Event]:
        payload = {
            "model": self.model,
            "messages": self._format_messages(messages),
            "stream": True,
            **({"tools": tools} if tools else {}),
        }
        async for event in self._stream_response(payload):
            yield event


class OllamaEmbeddingProvider(BaseHTTPProvider):
    """Provider that calls Ollama's /api/embed to generate embeddings."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout: float = 60.0,
    ) -> None:
        super().__init__(base_url=base_url, timeout=timeout)
        self.model = model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Fetch embeddings for a list of text strings from Ollama."""
        payload = {"model": self.model, "input": texts}
        async with self._get_client() as client:
            response = await client.post("/api/embed", json=payload)
            await self._check_response_status(response)
            data = response.json()
            return data.get("embeddings", [])

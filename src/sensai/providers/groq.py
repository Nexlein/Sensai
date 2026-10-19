import json
import os
from collections import deque
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from sensai.domain.errors import ProviderError
from sensai.domain.events import Event, TextChunkEvent, ToolCallEvent
from sensai.domain.models import Message
from sensai.providers.base import BaseHTTPProvider

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_API_KEY_ENV = "GROQ_API_KEY"


class GroqLLMProvider(BaseHTTPProvider):
    """Groq's OpenAI-compatible chat API. Opt-in: Ollama stays the default."""

    def __init__(
        self,
        model: str = "openai/gpt-oss-120b",
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        key = api_key or os.environ.get(GROQ_API_KEY_ENV)
        if not key:
            raise ProviderError(
                f"Groq needs an API key: set {GROQ_API_KEY_ENV} or api_key in sensai.toml."
            )
        super().__init__(base_url=GROQ_BASE_URL, timeout=timeout)
        self.model = model
        self._api_key = key

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    def _format_message(self, msg: Message) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in msg.tool_calls
            ]
        return payload

    def _format_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Associate tool results with the preceding assistant tool call ids."""
        formatted: list[dict[str, Any]] = []
        pending_ids: deque[str] = deque()
        for message in messages:
            payload = self._format_message(message)
            if message.role == "assistant":
                pending_ids = deque(tc.id for tc in message.tool_calls or [])
            elif message.role == "tool" and pending_ids:
                payload["tool_call_id"] = pending_ids.popleft()
            formatted.append(payload)
        return formatted

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        status = response.status_code
        try:
            detail = response.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            detail = response.text.strip()
        if status == 401:
            return "Groq rejected the API key (401). Check GROQ_API_KEY."
        if status == 429:
            # Groq's message names the limit hit (tokens or requests per minute).
            retry = response.headers.get("retry-after")
            wait = f" Retry in {retry}s." if retry else ""
            return f"Groq rate limit reached (429): {detail}{wait}"
        return f"Groq error [{status}]: {detail}"

    @staticmethod
    def _tool_call_event(call: dict[str, str]) -> ToolCallEvent:
        raw = call["arguments"].strip()
        try:
            arguments = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"Groq sent malformed arguments for tool '{call['name']}': {exc}"
            ) from exc
        if not isinstance(arguments, dict):
            raise ProviderError(
                f"Groq sent non-object arguments for tool '{call['name']}'."
            )
        return ToolCallEvent(tool_name=call["name"], arguments=arguments)

    async def _stream_response(self, payload: dict[str, Any]) -> AsyncGenerator[Event]:
        # Tool calls arrive as fragments keyed by index; emit them once complete.
        calls: dict[int, dict[str, str]] = {}
        try:
            async with (
                self._get_client() as client,
                client.stream("POST", "/chat/completions", json=payload) as response,
            ):
                if response.is_error:
                    await response.aread()
                    raise ProviderError(self._error_message(response))
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if "error" in chunk:
                        message = chunk["error"].get("message", chunk["error"])
                        raise ProviderError(f"Groq error: {message}")
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if content := delta.get("content"):
                            yield TextChunkEvent(content=content)
                        for fragment in delta.get("tool_calls") or []:
                            call = calls.setdefault(
                                fragment.get("index", 0), {"name": "", "arguments": ""}
                            )
                            function = fragment.get("function") or {}
                            call["name"] += function.get("name") or ""
                            call["arguments"] += function.get("arguments") or ""
        except httpx.TimeoutException as exc:
            raise ProviderError("Groq request timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach Groq: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Groq sent an unreadable stream: {exc}") from exc

        for index in sorted(calls):
            yield self._tool_call_event(calls[index])

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        think: bool | str | None = None,
    ) -> AsyncGenerator[Event]:
        payload = {
            "model": self.model,
            "messages": self._format_messages(messages),
            "stream": True,
            **({"tools": tools} if tools else {}),
        }
        async for event in self._stream_response(payload):
            yield event

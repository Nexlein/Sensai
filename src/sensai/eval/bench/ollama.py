"""A small synchronous client of the Ollama HTTP API, for measuring models.

Unlike `OllamaLLMProvider`, it waits for whole answers and keeps the server's
own counters (tokens and nanosecond durations), which is what a benchmark needs.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_URL = "http://localhost:11434"


@dataclass(frozen=True)
class ChatResult:
    """One `/api/chat` answer with the server's counters, durations in seconds."""

    content: str
    thinking: str
    tool_calls: list[dict[str, Any]]
    prompt_tokens: int
    reply_tokens: int
    load_seconds: float
    prompt_seconds: float
    reply_seconds: float
    total_seconds: float
    wall_seconds: float

    @property
    def prompt_rate(self) -> float | None:
        return self.prompt_tokens / self.prompt_seconds if self.prompt_seconds else None

    @property
    def reply_rate(self) -> float | None:
        return self.reply_tokens / self.reply_seconds if self.reply_seconds else None

    @property
    def first_token_seconds(self) -> float:
        return self.load_seconds + self.prompt_seconds

    @property
    def tool_names(self) -> list[str]:
        return [call.get("function", {}).get("name", "") for call in self.tool_calls]


@dataclass(frozen=True)
class Loaded:
    """One entry of `/api/ps`: bytes in memory, bytes in VRAM, context size."""

    name: str
    size: int
    size_vram: int
    context_length: int | None
    details: dict[str, Any] = field(default_factory=dict)


def _seconds(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    return value / 1e9 if isinstance(value, int | float) else 0.0


class OllamaBench:
    """Blocking calls to one Ollama server."""

    def __init__(
        self, base_url: str = DEFAULT_URL, client: httpx.Client | None = None
    ) -> None:
        self.client = client or httpx.Client(
            base_url=base_url, timeout=httpx.Timeout(30.0, read=None)
        )
        self._capabilities: dict[str, list[str]] = {}

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think
        if tools:
            payload["tools"] = tools
        start = time.perf_counter()
        response = self.client.post("/api/chat", json=payload)
        wall = time.perf_counter() - start
        if response.is_error:
            raise RuntimeError(
                f"Ollama error [{response.status_code}]: {response.text}"
            )
        data = response.json()
        message = data.get("message") or {}
        return ChatResult(
            content=message.get("content") or "",
            thinking=message.get("thinking") or "",
            tool_calls=message.get("tool_calls") or [],
            prompt_tokens=data.get("prompt_eval_count") or 0,
            reply_tokens=data.get("eval_count") or 0,
            load_seconds=_seconds(data, "load_duration"),
            prompt_seconds=_seconds(data, "prompt_eval_duration"),
            reply_seconds=_seconds(data, "eval_duration"),
            total_seconds=_seconds(data, "total_duration"),
            wall_seconds=wall,
        )

    def loaded(self) -> list[Loaded]:
        response = self.client.get("/api/ps")
        response.raise_for_status()
        return [
            Loaded(
                name=entry.get("name", ""),
                size=entry.get("size", 0),
                size_vram=entry.get("size_vram", 0),
                context_length=entry.get("context_length"),
                details=entry.get("details") or {},
            )
            for entry in response.json().get("models") or []
        ]

    def unload(self, model: str) -> None:
        """Ask the server to drop `model` from memory now."""
        self.client.post("/api/generate", json={"model": model, "keep_alive": 0})

    def unload_all(self) -> None:
        for entry in self.loaded():
            self.unload(entry.name)

    def capabilities(self, model: str) -> list[str]:
        """What the model can do: `completion`, `tools`, `thinking`, `vision`..."""
        if model not in self._capabilities:
            response = self.client.post("/api/show", json={"model": model})
            response.raise_for_status()
            self._capabilities[model] = response.json().get("capabilities") or []
        return self._capabilities[model]

    def installed(self) -> list[str]:
        response = self.client.get("/api/tags")
        response.raise_for_status()
        return sorted(entry["name"] for entry in response.json().get("models") or [])

    def embed(self, model: str, texts: list[str]) -> tuple[list[list[float]], float]:
        start = time.perf_counter()
        response = self.client.post("/api/embed", json={"model": model, "input": texts})
        response.raise_for_status()
        return response.json().get("embeddings", []), time.perf_counter() - start

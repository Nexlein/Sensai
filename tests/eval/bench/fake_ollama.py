"""An in-process Ollama server for benchmark tests."""

import json
from collections.abc import Callable
from typing import Any

import httpx

from sensai.eval.bench.ollama import OllamaBench

Reply = Callable[[dict[str, Any]], dict[str, Any]]


def answer(
    content: str = "ok", tool: str | None = None, **counters: Any
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool is not None:
        message["tool_calls"] = [
            {"function": {"name": tool, "arguments": counters.pop("arguments", {})}}
        ]
    return {
        "message": message,
        "done": True,
        "prompt_eval_count": counters.get("prompt_tokens", 100),
        "eval_count": counters.get("reply_tokens", 50),
        "load_duration": 1_000_000_000,
        "prompt_eval_duration": 500_000_000,
        "eval_duration": 2_000_000_000,
        "total_duration": 3_500_000_000,
    }


class FakeOllama:
    """Records requests and answers them like Ollama would."""

    def __init__(
        self, reply: Reply | None = None, capabilities: list[str] | None = None
    ) -> None:
        self.reply = reply or (lambda payload: answer())
        self.capabilities = (
            capabilities
            if capabilities is not None
            else ["completion", "tools", "thinking"]
        )
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.loaded: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        path = request.url.path
        self.requests.append((path, payload))
        if path == "/api/chat":
            if payload["model"] not in self.loaded:
                self.loaded.append(payload["model"])
            return httpx.Response(200, json=self.reply(payload))
        if path == "/api/ps":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": m,
                            "size": 3_000_000_000,
                            "size_vram": 0,
                            "context_length": 4096,
                            "details": {
                                "parameter_size": "4B",
                                "quantization_level": "Q4_K_M",
                            },
                        }
                        for m in self.loaded
                    ]
                },
            )
        if path == "/api/generate":
            self.loaded = [m for m in self.loaded if m != payload["model"]]
            return httpx.Response(200, json={})
        if path == "/api/show":
            return httpx.Response(200, json={"capabilities": self.capabilities})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "b"}, {"name": "a"}]})
        if path == "/api/embed":
            return httpx.Response(
                200, json={"embeddings": [[1.0, 0.0] for _ in payload["input"]]}
            )
        return httpx.Response(404)

    def client(self) -> OllamaBench:
        transport = httpx.MockTransport(self.handle)
        return OllamaBench(
            client=httpx.Client(transport=transport, base_url="http://ollama")
        )

    def chats(self) -> list[dict[str, Any]]:
        return [payload for path, payload in self.requests if path == "/api/chat"]

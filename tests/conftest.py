"""Session harness shared by the functional and live suites.

`start_session` wires config, tools, memory, guardrails and persistence exactly as
the CLI does, through `build_session`. `say` sends one input through
`process_input`, the entry point every frontend shares, and keeps what it produced.
"""

import textwrap
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from sensai.core.bootstrap import build_session
from sensai.core.commands import CommandContext, CommandResult
from sensai.core.input import process_input
from sensai.domain.events import Event, TextChunkEvent, ToolCallEvent
from sensai.domain.models import ToolCall


@dataclass
class Exchange:
    """Everything one input produced, as a frontend would have seen it."""

    prompt: str
    result: CommandResult
    events: list[Event] = field(default_factory=list)
    confirmations: list[ToolCall] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(e.content for e in self.events if isinstance(e, TextChunkEvent))

    @property
    def tool_calls(self) -> list[ToolCallEvent]:
        return self.of(ToolCallEvent)

    def of(self, kind: type[Event]) -> list:
        return [e for e in self.events if isinstance(e, kind)]

    def transcript(self) -> str:
        lines = [f"user: {self.prompt}"]
        lines += [f"  tool {c.tool_name}({c.arguments})" for c in self.tool_calls]
        lines.append(f"sensai: {self.text or self.result.message}")
        return "\n".join(lines)


@pytest.fixture
def today(monkeypatch):
    """Freeze the date the prompt gives the model: Monday 2026-10-26."""

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 26)

    monkeypatch.setattr("sensai.core.prompt.date", FrozenDate)
    return FrozenDate.today()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Empty project dir and cwd: `.sensai/`, logs and the fs root land here."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
async def start_session(workspace):
    """Factory: `await start_session(config_toml, provider=None, **build_args)`.

    A given `provider` replaces the configured one after the build.
    """
    opened: list[CommandContext] = []

    async def start(config: str, provider=None, **kwargs) -> CommandContext:
        path = workspace / "sensai.toml"
        path.write_text(textwrap.dedent(config), encoding="utf-8")
        context = await build_session(config_path=path, **kwargs)
        if provider is not None:
            context.engine.provider = provider
        opened.append(context)
        return context

    yield start
    for context in opened:
        await context.aclose()


@pytest.fixture
def say():
    """`await say(context, text, approve=True)`: one input, as typed by the user."""

    async def say_(context: CommandContext, text: str, approve: bool = True):
        exchange = Exchange(prompt=text, result=CommandResult())

        async def render(events):
            async for event in events:
                exchange.events.append(event)

        async def confirm(tc: ToolCall) -> bool:
            exchange.confirmations.append(tc)
            return approve

        exchange.result = await process_input(context, text, render, confirm)
        return exchange

    return say_


@pytest.fixture
def route_search(monkeypatch):
    """`route_search(handler)`: send the web_search tool's HTTP calls to `handler`.

    Only `sensai.tools.web` sees the swap; the model's own client is untouched.
    """

    def route(handler) -> None:
        real_client = httpx.AsyncClient

        class SearchHttpx:
            def __getattr__(self, name):
                return getattr(httpx, name)

            @staticmethod
            def AsyncClient(*args, **kwargs):
                transport = httpx.MockTransport(handler)
                return real_client(*args, transport=transport, **kwargs)

        monkeypatch.setattr("sensai.tools.web.httpx", SearchHttpx())

    return route


@pytest.fixture
def searxng(route_search):
    """Fake SearXNG answering every query with `searxng.results`; queries recorded."""
    fake = SimpleNamespace(
        results=[
            {
                "title": "Python 3.15 released",
                "url": "https://www.python.org/downloads/release/python-3150/",
                "content": "Python 3.15.0 is the newest major release.",
            }
        ],
        queries=[],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        fake.queries.append(request.url.params["q"])
        return httpx.Response(200, json={"results": fake.results})

    route_search(handler)
    return fake

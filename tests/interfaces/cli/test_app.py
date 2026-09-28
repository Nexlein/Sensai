from collections.abc import AsyncIterator
from pathlib import Path

from rich.console import Console

from sensai.core.commands import CommandContext
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event
from sensai.interfaces.cli.app import (
    _build_tool_registry,
    _run,
    resolve_config_path,
    resolve_session,
    run_repl,
)
from sensai.providers import get_provider
from sensai.providers.mock import MockLLMProvider


async def _drain(events: AsyncIterator[Event]) -> list[Event]:
    return [e async for e in events]


from sensai.tools.registry import ToolRegistry


def _script_stdin(monkeypatch, inputs):
    answers = iter(inputs)

    def fake_input(self, prompt=""):
        try:
            return next(answers)
        except StopIteration as exc:
            raise EOFError from exc

    monkeypatch.setattr(Console, "input", fake_input)


async def test_chat_streams_mock_provider_reply_until_exit(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, ["hello", "/exit"])

    code = await _run(["chat", "--provider", "mock"])

    out = capsys.readouterr().out
    assert code == 0
    assert "sensai:" in out
    assert "This is a mocked response from SENSAI." in out


async def test_chat_exits_cleanly_on_eof(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, [])

    code = await _run(["chat", "--provider", "mock"])

    assert code == 0


async def test_chat_reports_empty_input_and_continues(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, ["", "/exit"])

    code = await _run(["chat", "--provider", "mock"])

    assert code == 0
    assert "Empty input" in capsys.readouterr().out


async def test_chat_rejects_unknown_provider(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    code = await _run(["chat", "--provider", "does-not-exist"])

    assert code == 1
    assert "Unknown provider" in capsys.readouterr().out


async def test_chat_rejects_malformed_config_file(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad_config = tmp_path / "sensai.toml"
    bad_config.write_text("not [ valid toml")

    code = await _run(["chat", "--provider", "mock", "--config", str(bad_config)])

    assert code == 1
    assert "Malformed config file" in capsys.readouterr().out


async def test_chat_session_resumes_across_restarts(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, ["hello", "/exit"])
    code = await _run(["chat", "--provider", "mock", "--session", "my-session"])
    assert code == 0

    from sensai.memory.session import SqliteMemoryStore

    store = SqliteMemoryStore()
    conversation = await store.load("my-session")
    assert conversation is not None
    assert conversation.id == "my-session"
    assert [m.content for m in conversation.messages] == [
        "hello",
        "This is a mocked response from SENSAI.",
    ]


async def test_chat_session_resume_prints_prior_messages(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, ["hello", "/exit"])
    await _run(["chat", "--provider", "mock", "--session", "my-session"])
    capsys.readouterr()

    _script_stdin(monkeypatch, ["/exit"])
    code = await _run(["chat", "--provider", "mock", "--session", "my-session"])

    out = capsys.readouterr().out
    assert code == 0
    assert "hello" in out
    assert "This is a mocked response from SENSAI." in out


async def test_chat_session_unknown_name_creates_new(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, ["hi", "/exit"])
    code = await _run(["chat", "--provider", "mock", "--session", "brand-new"])
    assert code == 0

    from sensai.memory.session import SqliteMemoryStore

    store = SqliteMemoryStore()
    conversation = await store.load("brand-new")
    assert conversation is not None
    assert conversation.id == "brand-new"


def test_build_tool_registry_is_empty_when_root_is_unset():
    assert _build_tool_registry(None).get_tools_schema() == []


def test_build_tool_registry_registers_file_tools(tmp_path):
    schemas = _build_tool_registry(str(tmp_path)).get_tools_schema()

    assert {schema["function"]["name"] for schema in schemas} == {
        "read_file",
        "list_dir",
    }


def test_resolve_session_returns_name_when_given():
    assert resolve_session(["chat", "--session", "my-session"]) == "my-session"


def test_resolve_session_returns_none_when_absent():
    assert resolve_session(["chat"]) is None


def test_resolve_config_path_returns_custom_path():
    assert resolve_config_path(["chat", "--config", "custom.toml"]) == Path(
        "custom.toml"
    )


from sensai.core.config import AppConfig
from sensai.core.engine import ChatEngine
from sensai.domain.models import Conversation


class FakeMemoryStore:
    def __init__(self) -> None:
        self.saved: list[Conversation] = []

    async def save(self, conversation: Conversation) -> None:
        self.saved.append(conversation)

    async def load(self, conversation_id: str) -> Conversation | None:
        return None


def _context() -> CommandContext:
    config = AppConfig()
    return CommandContext(
        config=config,
        engine=ChatEngine(
            provider=MockLLMProvider(default_response="hi"),
            conversation=Conversation(),
            registry=None,
        ),
        provider_factory=lambda *args, **kwargs: None,
        tool_registry=None,
        tool_registry_factory=lambda _: None,
        memory_store=FakeMemoryStore(),
    )


async def test_run_repl_sends_each_line_until_eof():
    inputs = iter(["hello", "world"])
    sent: list[str] = []

    def read_input() -> str:
        try:
            return next(inputs)
        except StopIteration as exc:
            raise EOFError from exc

    async def render(events: AsyncIterator[Event]) -> None:
        sent.append("".join(e.content for e in await _drain(events)))

    errors: list[Exception] = []

    await run_repl(
        _context(), read_input=read_input, render=render, on_error=errors.append
    )

    assert sent == ["hi", "hi"]
    assert errors == []


async def test_run_repl_treats_bare_exit_as_chat_message():
    inputs = iter(["exit", "/exit"])
    rendered: list[str] = []

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        rendered.append("".join(e.content for e in await _drain(events)))

    await run_repl(
        _context(),
        read_input=read_input,
        render=render,
        on_error=lambda exc: None,
    )

    assert rendered == ["hi"]


async def test_run_repl_stops_on_slash_exit_command():
    inputs = iter(["/exit"])
    calls = 0

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        nonlocal calls
        calls += 1

    await run_repl(
        _context(), read_input=read_input, render=render, on_error=lambda exc: None
    )

    assert calls == 0


async def test_run_repl_stops_on_eof():
    def read_input() -> str:
        raise EOFError

    async def render(events: AsyncIterator[Event]) -> None:
        raise AssertionError("should not be called")

    await run_repl(
        _context(), read_input=read_input, render=render, on_error=lambda exc: None
    )


async def test_run_repl_reports_empty_input_and_continues():
    inputs = iter(["", "/exit"])
    errors: list[Exception] = []

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        async for _ in events:
            pass

    await run_repl(
        _context(), read_input=read_input, render=render, on_error=errors.append
    )

    assert len(errors) == 1
    assert isinstance(errors[0], EmptyInputError)


async def test_run_repl_reports_provider_error_and_continues():
    class FailingProvider:
        async def chat_stream(self, messages, tools=None):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    engine = ChatEngine(FailingProvider(), Conversation())
    context = CommandContext(
        config=AppConfig(),
        engine=engine,
        provider_factory=get_provider,
        tool_registry=ToolRegistry(),
        tool_registry_factory=lambda _: ToolRegistry(),
        memory_store=FakeMemoryStore(),
    )
    inputs = iter(["hi", "/exit"])
    errors: list[Exception] = []

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        async for _ in events:
            pass

    await run_repl(
        context, read_input=read_input, render=render, on_error=errors.append
    )

    assert len(errors) == 1
    assert isinstance(errors[0], ProviderError)

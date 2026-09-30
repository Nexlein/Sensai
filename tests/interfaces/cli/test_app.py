from collections.abc import AsyncIterator
from pathlib import Path
from typing import ClassVar

from rich.console import Console

from sensai.core.commands import CommandContext
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, TextChunkEvent
from sensai.interfaces.cli.app import run_repl
from sensai.interfaces.dispatcher import dispatch as _run
from sensai.interfaces.dispatcher import resolve_config_path, resolve_session
from sensai.providers import get_provider
from sensai.providers.mock import MockLLMProvider
from sensai.tools.registry import build_default_registry


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


def test_build_tool_registry_keeps_web_search_when_root_is_unset():
    schemas = build_default_registry(None).get_tools_schema()
    assert [schema["function"]["name"] for schema in schemas] == ["web_search"]


def test_build_tool_registry_registers_file_tools(tmp_path):
    schemas = build_default_registry(str(tmp_path)).get_tools_schema()

    assert {schema["function"]["name"] for schema in schemas} == {
        "read_file",
        "list_dir",
        "web_search",
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
        sent.append(
            "".join(
                e.content for e in await _drain(events) if isinstance(e, TextChunkEvent)
            )
        )

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
        rendered.append(
            "".join(
                e.content for e in await _drain(events) if isinstance(e, TextChunkEvent)
            )
        )

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


async def test_chat_rag_option_indexes_local_documents(monkeypatch, tmp_path):
    from sensai.memory.rag.store import SQLiteVectorStore

    class FakeEmbeddingProvider:
        def __init__(self, base_url: str, model: str):
            self.base_url = base_url
            self.model = model

        async def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("project guide", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sensai.core.bootstrap.OllamaEmbeddingProvider", FakeEmbeddingProvider
    )
    _script_stdin(monkeypatch, ["/exit"])

    code = await _run(
        ["chat", "--provider", "mock", "--rag-dir", str(docs), "--rag-db", "rag.db"]
    )

    assert code == 0
    results = SQLiteVectorStore("rag.db").search([1.0, 0.0])
    assert [chunk.text for chunk in results] == ["project guide"]


async def test_ui_flag_dispatches_to_tui(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    selected = []

    async def fake_run_tui(context):
        selected.append(context.config.interface)

    monkeypatch.setattr("sensai.interfaces.dispatcher.run_tui", fake_run_tui)

    code = await _run(["chat", "--provider", "mock", "--ui", "tui"])

    assert code == 0
    assert selected == ["tui"]


async def test_ui_flag_overrides_config_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sensai.toml"
    config_path.write_text('interface = "tui"\nprovider = "mock"\n')
    _script_stdin(monkeypatch, ["/exit"])

    code = await _run(["chat", "--config", str(config_path), "--ui", "cli"])

    assert code == 0


async def test_web_ui_reports_not_implemented(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)

    code = await _run(["chat", "--provider", "mock", "--ui", "web"])

    assert code == 1
    assert "not implemented" in capsys.readouterr().out


async def test_cli_confirmation_then_followup_keeps_chat_working(monkeypatch):
    from io import StringIO

    from sensai.domain.events import TextChunkEvent, ToolCallEvent
    from sensai.interfaces.cli.app import run_cli
    from sensai.tools.base import Tool

    executed = []

    class SearchTool(Tool):
        name = "web_search"
        description = "Search"
        parameters_schema: ClassVar[dict] = {}
        requires_confirmation = True

        async def execute(self, **kwargs):
            executed.append(kwargs)
            return "Result"

    class Provider:
        async def chat_stream(self, messages, tools=None):
            if messages[-1].role == "user" and messages[-1].content == "cherche":
                yield TextChunkEvent(content="Je vais chercher.")
                yield ToolCallEvent(
                    tool_name="web_search", arguments={"query": "Sensai"}
                )
            else:
                yield TextChunkEvent(content="Réponse terminée.")

    for answer, expected_executions in [("oui", 1), ("", 1), ("non", 0)]:
        executed.clear()
        context = _context()
        context.engine.provider = Provider()
        registry = ToolRegistry()
        registry.register(SearchTool())
        context.engine.registry = registry
        inputs = iter(["cherche", answer, "bonjour", "/exit"])
        monkeypatch.setattr("builtins.input", lambda values=inputs: next(values))
        output = StringIO()
        await run_cli(context, Console(file=output, force_terminal=False))
        assert len(executed) == expected_executions
        rendered = output.getvalue()
        assert rendered.count("Autoriser web_search ? [O/n]") == 1
        assert rendered.count("Réponse terminée.") == (2 if expected_executions else 1)
        assert "you: \nsensai:" in rendered
        assert "Réponse terminée.\n\nyou:" in rendered
        assert len(context.memory_store.saved) == 2
        assert context.engine.conversation.messages[-2].content == "bonjour"

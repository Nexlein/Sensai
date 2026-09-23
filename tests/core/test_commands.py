from collections.abc import AsyncIterator

import pytest

from sensai.core.commands import (
    CommandContext,
    ParsedCommand,
    dispatch_command,
    parse_commands,
    run_repl,
)
from sensai.core.config import AppConfig, load_config
from sensai.core.engine import ChatEngine
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event
from sensai.domain.models import Conversation
from sensai.domain.protocols import LLMProvider
from sensai.providers import get_provider
from sensai.providers.mock import MockLLMProvider
from sensai.tools.registry import ToolRegistry


class FakeMemoryStore:
    def __init__(self) -> None:
        self.saved: list[Conversation] = []

    async def save(self, conversation: Conversation) -> None:
        self.saved.append(conversation)

    async def load(self, conversation_id: str) -> Conversation | None:
        return None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hello", None),
        ("exit", None),
        ("hello /exit", None),
        ("/", None),
        ("/help", ParsedCommand(name="help", arguments=())),
        ("  /EXIT  ", ParsedCommand(name="exit", arguments=())),
        (
            "/config set model llama3.2",
            ParsedCommand(name="config", arguments=("set", "model", "llama3.2")),
        ),
    ],
)
def test_parse_commands(text, expected):
    assert parse_commands(text) == expected


def _engine(response: str = "hi") -> ChatEngine:
    return ChatEngine(MockLLMProvider(default_response=response), Conversation())


def _context(response: str = "hi", output: list[str] | None = None) -> CommandContext:
    messages = output if output is not None else []
    registry = ToolRegistry()
    engine = _engine(response)
    engine.registry = registry
    return CommandContext(
        config=AppConfig(),
        engine=engine,
        output=messages.append,
        provider_factory=get_provider,
        tool_registry=registry,
        tool_registry_factory=lambda _: ToolRegistry(),
        memory_store=FakeMemoryStore(),
    )


async def _drain(events: AsyncIterator[Event]) -> list[Event]:
    return [event async for event in events]


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
        output=lambda _: None,
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


async def test_dispatch_exit_requests_repl_exit():
    should_exit = await dispatch_command(
        ParsedCommand(name="exit", arguments=()),
        _context(),
    )

    assert should_exit


async def test_dispatch_unknown_command_reports_error_and_continues():
    output: list[str] = []

    should_exit = await dispatch_command(
        ParsedCommand(name="unknown", arguments=()),
        _context(output=output),
    )

    assert not should_exit
    assert output == ["Unknown command: /unknown"]


async def test_dispatch_clear_empties_current_conversation():
    output: list[str] = []
    context = _context(output=output)
    context.engine.conversation.add_message(role="user", content="hello")

    should_exit = await dispatch_command(
        ParsedCommand(name="clear", arguments=()),
        context,
    )

    assert not should_exit
    assert context.engine.conversation.messages == []
    assert output == ["Conversation cleared."]


async def test_dispatch_help_lists_commands():
    output: list[str] = []

    should_exit = await dispatch_command(
        ParsedCommand(name="help", arguments=()),
        _context(output=output),
    )

    assert not should_exit
    assert output == [
        """Available commands:
/exit - Exit the interactive session
/help - Show available commands
/clear - Clear the current conversation history
/new - Start and persist a new conversation
/model - Switch model for subsequent turns
/provider - Switch LLM provider
/config - View or update runtime configuration"""
    ]


async def test_dispatch_model_requires_exactly_one_name():
    output: list[str] = []
    context = _context(output=output)
    original_provider = context.engine.provider

    should_exit = await dispatch_command(
        ParsedCommand(name="model", arguments=()),
        context,
    )

    assert not should_exit
    assert context.engine.provider is original_provider
    assert output == ["Usage: /model <name>"]


async def test_dispatch_model_switches_provider_and_preserves_conversation():
    output: list[str] = []
    replacement = MockLLMProvider(default_response="new model")
    calls: list[tuple[str, dict[str, str]]] = []

    def provider_factory(name: str, **config: str) -> LLMProvider:
        calls.append((name, config))
        return replacement

    context = _context(output=output)
    context.provider_factory = provider_factory
    context.engine.conversation.add_message(role="user", content="existing history")
    conversation = context.engine.conversation
    messages = list(conversation.messages)

    should_exit = await dispatch_command(
        ParsedCommand(name="model", arguments=("llama3.2:latest",)),
        context,
    )

    assert not should_exit
    assert calls == [
        (
            "ollama",
            {
                "model": "llama3.2:latest",
                "base_url": "http://localhost:11434",
            },
        )
    ]
    assert context.engine.provider is replacement
    assert context.engine.conversation is conversation
    assert context.engine.conversation.messages == messages
    assert context.config.model == "llama3.2:latest"
    assert output == ["Model switched to llama3.2:latest."]


async def test_dispatch_provider_requires_exactly_one_name():
    output: list[str] = []
    context = _context(output=output)
    original_provider = context.engine.provider

    should_exit = await dispatch_command(
        ParsedCommand(name="provider", arguments=()),
        context,
    )

    assert not should_exit
    assert context.engine.provider is original_provider
    assert context.config.provider == "ollama"
    assert output == ["Usage: /provider <name>"]


async def test_dispatch_provider_switches_provider_and_preserves_conversation():
    output: list[str] = []
    replacement = MockLLMProvider(default_response="replacement")
    calls: list[tuple[str, dict[str, str]]] = []

    def provider_factory(name: str, **config: str) -> LLMProvider:
        calls.append((name, config))
        return replacement

    context = _context(output=output)
    context.provider_factory = provider_factory
    context.engine.conversation.add_message(role="user", content="existing history")
    conversation = context.engine.conversation
    messages = list(conversation.messages)

    should_exit = await dispatch_command(
        ParsedCommand(name="provider", arguments=("MOCK",)),
        context,
    )

    assert not should_exit
    assert calls == [
        (
            "mock",
            {
                "model": "llama3.2",
                "base_url": "http://localhost:11434",
            },
        )
    ]
    assert context.engine.provider is replacement
    assert context.engine.conversation is conversation
    assert context.engine.conversation.messages == messages
    assert context.config.provider == "mock"
    assert context.config.model == "llama3.2"
    assert output == ["Provider switched to mock."]


async def test_dispatch_unknown_provider_preserves_current_provider():
    output: list[str] = []
    context = _context(output=output)
    original_provider = context.engine.provider

    should_exit = await dispatch_command(
        ParsedCommand(name="provider", arguments=("missing",)),
        context,
    )

    assert not should_exit
    assert context.engine.provider is original_provider
    assert context.config.provider == "ollama"
    assert output == [
        "Unknown provider 'missing'. Available providers: ['mock', 'ollama']"
    ]


async def test_dispatch_config_gets_all_values():
    output: list[str] = []
    context = _context(output=output)

    should_exit = await dispatch_command(
        ParsedCommand(name="config", arguments=("get",)),
        context,
    )

    assert not should_exit
    assert output == [str(context.config.model_dump())]


async def test_dispatch_config_gets_one_value():
    output: list[str] = []

    should_exit = await dispatch_command(
        ParsedCommand(name="config", arguments=("get", "model")),
        _context(output=output),
    )

    assert not should_exit
    assert output == ["model = llama3.2"]


async def test_dispatch_config_rejects_unknown_key():
    output: list[str] = []

    should_exit = await dispatch_command(
        ParsedCommand(name="config", arguments=("get", "missing")),
        _context(output=output),
    )

    assert not should_exit
    assert output == ["Unknown config key: missing"]


async def test_dispatch_config_set_model_reuses_model_handler():
    output: list[str] = []
    replacement = MockLLMProvider(default_response="replacement")
    calls: list[tuple[str, dict[str, str]]] = []

    def provider_factory(name: str, **config: str) -> LLMProvider:
        calls.append((name, config))
        return replacement

    context = _context(output=output)
    context.provider_factory = provider_factory

    should_exit = await dispatch_command(
        ParsedCommand(name="config", arguments=("set", "model", "mistral")),
        context,
    )

    assert not should_exit
    assert calls == [
        (
            "ollama",
            {
                "model": "mistral",
                "base_url": "http://localhost:11434",
            },
        )
    ]
    assert context.engine.provider is replacement
    assert context.config.model == "mistral"
    assert output == ["Model switched to mistral."]


async def test_dispatch_config_set_base_url_rebuilds_provider():
    output: list[str] = []
    replacement = MockLLMProvider(default_response="replacement")
    calls: list[tuple[str, dict[str, str]]] = []

    def provider_factory(name: str, **config: str) -> LLMProvider:
        calls.append((name, config))
        return replacement

    context = _context(output=output)
    context.provider_factory = provider_factory
    conversation = context.engine.conversation

    should_exit = await dispatch_command(
        ParsedCommand(
            name="config",
            arguments=("set", "base_url", "http://ollama.example:11434"),
        ),
        context,
    )

    assert not should_exit
    assert calls == [
        (
            "ollama",
            {
                "model": "llama3.2",
                "base_url": "http://ollama.example:11434",
            },
        )
    ]
    assert context.engine.provider is replacement
    assert context.engine.conversation is conversation
    assert context.config.base_url == "http://ollama.example:11434"
    assert output == ["base_url = http://ollama.example:11434"]


async def test_dispatch_config_set_rejects_unknown_key():
    output: list[str] = []

    should_exit = await dispatch_command(
        ParsedCommand(name="config", arguments=("set", "missing", "value")),
        _context(output=output),
    )

    assert not should_exit
    assert output == ["Unknown config key: missing"]


async def test_dispatch_config_rejects_invalid_usage():
    output: list[str] = []

    should_exit = await dispatch_command(
        ParsedCommand(name="config", arguments=("set", "model")),
        _context(output=output),
    )

    assert not should_exit
    assert output == ["Usage: /config set <key> <value>"]


async def test_dispatch_config_save_persists_current_config(tmp_path):
    output: list[str] = []
    context = _context(output=output)
    context.config.model = "mistral"
    context.config.tools.fs_allowed_root = "/tmp/project"
    context.config_path = tmp_path / "sensai.toml"

    should_exit = await dispatch_command(
        ParsedCommand(name="config", arguments=("save",)),
        context,
    )

    assert not should_exit
    assert load_config(context.config_path) == context.config
    assert output == [f"Config saved to {context.config_path}."]


async def test_dispatch_config_save_rejects_arguments(tmp_path):
    output: list[str] = []
    context = _context(output=output)
    context.config_path = tmp_path / "sensai.toml"

    should_exit = await dispatch_command(
        ParsedCommand(name="config", arguments=("save", "extra")),
        context,
    )

    assert not should_exit
    assert not context.config_path.exists()
    assert output == ["Usage: /config save"]


async def test_dispatch_config_gets_nested_tool_value():
    output: list[str] = []
    context = _context(output=output)
    context.config.tools.fs_allowed_root = "/tmp/project"

    should_exit = await dispatch_command(
        ParsedCommand(
            name="config",
            arguments=("get", "tools.fs_allowed_root"),
        ),
        context,
    )

    assert not should_exit
    assert output == ["tools.fs_allowed_root = /tmp/project"]


async def test_dispatch_config_set_fs_root_replaces_active_registry():
    output: list[str] = []
    context = _context(output=output)
    original_registry = context.tool_registry
    replacement = ToolRegistry()
    roots: list[str | None] = []

    def registry_factory(root: str | None) -> ToolRegistry:
        roots.append(root)
        return replacement

    context.tool_registry_factory = registry_factory

    should_exit = await dispatch_command(
        ParsedCommand(
            name="config",
            arguments=("set", "tools.fs_allowed_root", "/tmp/project"),
        ),
        context,
    )

    assert not should_exit
    assert roots == ["/tmp/project"]
    assert context.tool_registry is replacement
    assert context.engine.registry is replacement
    assert context.tool_registry is not original_registry
    assert context.config.tools.fs_allowed_root == "/tmp/project"
    assert output == ["tools.fs_allowed_root = /tmp/project"]


async def test_dispatch_config_set_fs_root_none_disables_tools():
    output: list[str] = []
    context = _context(output=output)
    replacement = ToolRegistry()
    context.tool_registry_factory = lambda _: replacement

    should_exit = await dispatch_command(
        ParsedCommand(
            name="config",
            arguments=("set", "tools.fs_allowed_root", "none"),
        ),
        context,
    )

    assert not should_exit
    assert context.config.tools.fs_allowed_root is None
    assert context.engine.registry is replacement
    assert output == ["tools.fs_allowed_root = None"]


async def test_dispatch_new_persists_and_activates_fresh_conversation():
    output: list[str] = []
    context = _context(output=output)
    previous = context.engine.conversation
    previous.add_message(role="user", content="old history")
    store = context.memory_store
    assert isinstance(store, FakeMemoryStore)

    should_exit = await dispatch_command(
        ParsedCommand(name="new", arguments=()),
        context,
    )

    assert not should_exit
    assert context.engine.conversation is not previous
    assert context.engine.conversation.id != previous.id
    assert context.engine.conversation.messages == []
    assert store.saved == [context.engine.conversation]
    assert output == [f"Started new conversation: {context.engine.conversation.id}"]


async def test_dispatch_new_rejects_arguments():
    output: list[str] = []
    context = _context(output=output)
    previous = context.engine.conversation
    store = context.memory_store
    assert isinstance(store, FakeMemoryStore)

    should_exit = await dispatch_command(
        ParsedCommand(name="new", arguments=("name",)),
        context,
    )

    assert not should_exit
    assert context.engine.conversation is previous
    assert store.saved == []
    assert output == ["Usage: /new"]

from collections.abc import AsyncIterator

import pytest

from sensai.core.commands import (
    CommandContext,
    ParsedCommand,
    dispatch_command,
    parse_commands,
)
from sensai.core.config import DEFAULT_MODEL, AppConfig, load_config
from sensai.core.engine import ChatEngine
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


def _context(response: str = "hi") -> CommandContext:
    registry = ToolRegistry()
    engine = _engine(response)
    engine.registry = registry
    return CommandContext(
        config=AppConfig(),
        engine=engine,
        provider_factory=get_provider,
        tool_registry=registry,
        tool_registry_factory=lambda _: ToolRegistry(),
        memory_store=FakeMemoryStore(),
    )


async def _drain(events: AsyncIterator[Event]) -> list[Event]:
    return [event async for event in events]


async def test_dispatch_exit_requests_repl_exit():
    result = await dispatch_command(
        ParsedCommand(name="exit", arguments=()),
        _context(),
    )

    assert result.should_exit


async def test_dispatch_unknown_command_reports_error_and_continues():
    # output = []

    result = await dispatch_command(
        ParsedCommand(name="unknown", arguments=()),
        _context(),
    )

    assert not result.should_exit
    assert result.message == "Unknown command: /unknown"


async def test_dispatch_clear_empties_current_conversation():
    # output = []
    context = _context()
    context.engine.conversation.add_message(role="user", content="hello")

    result = await dispatch_command(
        ParsedCommand(name="clear", arguments=()),
        context,
    )

    assert not result.should_exit
    assert context.engine.conversation.messages == []
    assert context.memory_store.saved == [context.engine.conversation]
    assert result.message == "Conversation cleared."


async def test_dispatch_help_lists_commands():
    # output = []

    result = await dispatch_command(
        ParsedCommand(name="help", arguments=()),
        _context(),
    )

    assert not result.should_exit
    assert (
        result.message
        == """Available commands:
/exit - Exit the interactive session
/help - Show available commands
/clear - Clear the current conversation history
/new - Start and persist a new conversation
/memory - Inspect or manage long-term structured memory
/model - Switch model for subsequent turns
/provider - Switch LLM provider
/config - View or update runtime configuration"""
    )


async def test_dispatch_model_requires_exactly_one_name():
    # output = []
    context = _context()
    original_provider = context.engine.provider

    result = await dispatch_command(
        ParsedCommand(name="model", arguments=()),
        context,
    )

    assert not result.should_exit
    assert context.engine.provider is original_provider
    assert result.message == "Usage: /model <name>"


async def test_dispatch_model_switches_provider_and_preserves_conversation():
    # output = []
    replacement = MockLLMProvider(default_response="new model")
    calls: list[tuple[str, dict[str, str]]] = []

    def provider_factory(name: str, **config: str) -> LLMProvider:
        calls.append((name, config))
        return replacement

    context = _context()
    context.provider_factory = provider_factory
    context.engine.conversation.add_message(role="user", content="existing history")
    conversation = context.engine.conversation
    messages = list(conversation.messages)

    result = await dispatch_command(
        ParsedCommand(name="model", arguments=("llama3.2:latest",)),
        context,
    )

    assert not result.should_exit
    assert calls == [
        (
            "ollama",
            {
                "model": "llama3.2:latest",
                "base_url": "http://localhost:11434",
                "api_key": None,
            },
        )
    ]
    assert context.engine.provider is replacement
    assert context.engine.conversation is conversation
    assert context.engine.conversation.messages == messages
    assert context.config.model == "llama3.2:latest"
    assert result.message == "Model switched to llama3.2:latest."


async def test_dispatch_provider_requires_exactly_one_name():
    # output = []
    context = _context()
    original_provider = context.engine.provider

    result = await dispatch_command(
        ParsedCommand(name="provider", arguments=()),
        context,
    )

    assert not result.should_exit
    assert context.engine.provider is original_provider
    assert context.config.provider == "ollama"
    assert result.message == "Usage: /provider <name>"


async def test_dispatch_provider_switches_provider_and_preserves_conversation():
    # output = []
    replacement = MockLLMProvider(default_response="replacement")
    calls: list[tuple[str, dict[str, str]]] = []

    def provider_factory(name: str, **config: str) -> LLMProvider:
        calls.append((name, config))
        return replacement

    context = _context()
    context.provider_factory = provider_factory
    context.engine.conversation.add_message(role="user", content="existing history")
    conversation = context.engine.conversation
    messages = list(conversation.messages)

    result = await dispatch_command(
        ParsedCommand(name="provider", arguments=("MOCK",)),
        context,
    )

    assert not result.should_exit
    assert calls == [
        (
            "mock",
            {
                "model": DEFAULT_MODEL,
                "base_url": "http://localhost:11434",
                "api_key": None,
            },
        )
    ]
    assert context.engine.provider is replacement
    assert context.engine.conversation is conversation
    assert context.engine.conversation.messages == messages
    assert context.config.provider == "mock"
    assert context.config.model == DEFAULT_MODEL
    assert result.message == "Provider switched to mock."


async def test_dispatch_unknown_provider_preserves_current_provider():
    # output = []
    context = _context()
    original_provider = context.engine.provider

    result = await dispatch_command(
        ParsedCommand(name="provider", arguments=("missing",)),
        context,
    )

    assert not result.should_exit
    assert context.engine.provider is original_provider
    assert context.config.provider == "ollama"
    assert (
        result.message
        == "Unknown provider 'missing'. Available providers: ['groq', 'mock', 'ollama']"
    )


async def test_dispatch_config_gets_all_values():
    # output = []
    context = _context()

    result = await dispatch_command(
        ParsedCommand(name="config", arguments=("get",)),
        context,
    )

    assert not result.should_exit
    assert result.message == str(context.config.model_dump())


async def test_dispatch_config_masks_api_key():
    context = _context()
    context.config.api_key = "gsk_secret"

    for arguments in (("get",), (), ("get", "api_key")):
        result = await dispatch_command(
            ParsedCommand(name="config", arguments=arguments), context
        )
        assert "gsk_secret" not in result.message
        assert "***" in result.message


async def test_dispatch_provider_passes_api_key_to_factory():
    calls: list[tuple[str, dict[str, str | None]]] = []

    def provider_factory(name: str, **config: str | None) -> LLMProvider:
        calls.append((name, config))
        return MockLLMProvider()

    context = _context()
    context.provider_factory = provider_factory
    context.config.api_key = "gsk_secret"

    await dispatch_command(ParsedCommand(name="provider", arguments=("groq",)), context)

    assert calls[0][1]["api_key"] == "gsk_secret"


async def test_dispatch_config_gets_one_value():
    # output = []

    result = await dispatch_command(
        ParsedCommand(name="config", arguments=("get", "model")),
        _context(),
    )

    assert not result.should_exit
    assert result.message == f"model = {DEFAULT_MODEL}"


async def test_dispatch_config_rejects_unknown_key():
    # output = []

    result = await dispatch_command(
        ParsedCommand(name="config", arguments=("get", "missing")),
        _context(),
    )

    assert not result.should_exit
    assert result.message == "Unknown config key: missing"


async def test_dispatch_config_set_model_reuses_model_handler():
    # output = []
    replacement = MockLLMProvider(default_response="replacement")
    calls: list[tuple[str, dict[str, str]]] = []

    def provider_factory(name: str, **config: str) -> LLMProvider:
        calls.append((name, config))
        return replacement

    context = _context()
    context.provider_factory = provider_factory

    result = await dispatch_command(
        ParsedCommand(name="config", arguments=("set", "model", "mistral")),
        context,
    )

    assert not result.should_exit
    assert calls == [
        (
            "ollama",
            {
                "model": "mistral",
                "base_url": "http://localhost:11434",
                "api_key": None,
            },
        )
    ]
    assert context.engine.provider is replacement
    assert context.config.model == "mistral"
    assert result.message == "Model switched to mistral."


async def test_dispatch_config_set_base_url_rebuilds_provider():
    # output = []
    replacement = MockLLMProvider(default_response="replacement")
    calls: list[tuple[str, dict[str, str]]] = []

    def provider_factory(name: str, **config: str) -> LLMProvider:
        calls.append((name, config))
        return replacement

    context = _context()
    context.provider_factory = provider_factory
    conversation = context.engine.conversation

    result = await dispatch_command(
        ParsedCommand(
            name="config",
            arguments=("set", "base_url", "http://ollama.example:11434"),
        ),
        context,
    )

    assert not result.should_exit
    assert calls == [
        (
            "ollama",
            {
                "model": DEFAULT_MODEL,
                "base_url": "http://ollama.example:11434",
                "api_key": None,
            },
        )
    ]
    assert context.engine.provider is replacement
    assert context.engine.conversation is conversation
    assert context.config.base_url == "http://ollama.example:11434"
    assert result.message == "base_url = http://ollama.example:11434"


async def test_dispatch_config_set_rejects_unknown_key():
    # output = []

    result = await dispatch_command(
        ParsedCommand(name="config", arguments=("set", "missing", "value")),
        _context(),
    )

    assert not result.should_exit
    assert result.message == "Unknown config key: missing"


async def test_dispatch_config_rejects_invalid_usage():
    # output = []

    result = await dispatch_command(
        ParsedCommand(name="config", arguments=("set", "model")),
        _context(),
    )

    assert not result.should_exit
    assert result.message == "Usage: /config set <key> <value>"


async def test_dispatch_config_save_persists_current_config(tmp_path):
    # output = []
    context = _context()
    context.config.model = "mistral"
    context.config.tools.fs_allowed_root = "/tmp/project"
    context.config_path = tmp_path / "sensai.toml"

    result = await dispatch_command(
        ParsedCommand(name="config", arguments=("save",)),
        context,
    )

    assert not result.should_exit
    assert load_config(context.config_path) == context.config
    assert result.message == f"Config saved to {context.config_path}."


async def test_dispatch_config_save_rejects_arguments(tmp_path):
    # output = []
    context = _context()
    context.config_path = tmp_path / "sensai.toml"

    result = await dispatch_command(
        ParsedCommand(name="config", arguments=("save", "extra")),
        context,
    )

    assert not result.should_exit
    assert not context.config_path.exists()
    assert result.message == "Usage: /config save"


async def test_dispatch_config_gets_nested_tool_value():
    # output = []
    context = _context()
    context.config.tools.fs_allowed_root = "/tmp/project"

    result = await dispatch_command(
        ParsedCommand(
            name="config",
            arguments=("get", "tools.fs_allowed_root"),
        ),
        context,
    )

    assert not result.should_exit
    assert result.message == "tools.fs_allowed_root = /tmp/project"


async def test_dispatch_config_set_fs_root_replaces_active_registry():
    # output = []
    context = _context()
    original_registry = context.tool_registry
    replacement = ToolRegistry()
    roots: list[str | None] = []

    def registry_factory(root: str | None) -> ToolRegistry:
        roots.append(root)
        return replacement

    context.tool_registry_factory = registry_factory

    result = await dispatch_command(
        ParsedCommand(
            name="config",
            arguments=("set", "tools.fs_allowed_root", "/tmp/project"),
        ),
        context,
    )

    assert not result.should_exit
    assert roots == ["/tmp/project"]
    assert context.tool_registry is replacement
    assert context.engine.registry is replacement
    assert context.tool_registry is not original_registry
    assert context.config.tools.fs_allowed_root == "/tmp/project"
    assert result.message == "tools.fs_allowed_root = /tmp/project"


async def test_dispatch_config_set_fs_root_none_disables_tools():
    # output = []
    context = _context()
    replacement = ToolRegistry()
    context.tool_registry_factory = lambda _: replacement

    result = await dispatch_command(
        ParsedCommand(
            name="config",
            arguments=("set", "tools.fs_allowed_root", "none"),
        ),
        context,
    )

    assert not result.should_exit
    assert context.config.tools.fs_allowed_root is None
    assert context.engine.registry is replacement
    assert result.message == "tools.fs_allowed_root = None"


async def test_dispatch_new_persists_and_activates_fresh_conversation():
    # output = []
    context = _context()
    previous = context.engine.conversation
    previous.add_message(role="user", content="old history")
    store = context.memory_store
    assert isinstance(store, FakeMemoryStore)

    result = await dispatch_command(
        ParsedCommand(name="new", arguments=()),
        context,
    )

    assert not result.should_exit
    assert context.engine.conversation is not previous
    assert context.engine.conversation.id != previous.id
    assert context.engine.conversation.messages == []
    assert store.saved == [context.engine.conversation]
    assert (
        result.message == f"Started new conversation: {context.engine.conversation.id}"
    )


async def test_dispatch_new_rejects_arguments():
    # output = []
    context = _context()
    previous = context.engine.conversation
    store = context.memory_store
    assert isinstance(store, FakeMemoryStore)

    result = await dispatch_command(
        ParsedCommand(name="new", arguments=("name",)),
        context,
    )

    assert not result.should_exit
    assert context.engine.conversation is previous
    assert store.saved == []
    assert result.message == "Usage: /new"


async def test_dispatch_memory_unavailable():
    context = _context()
    context.structured_memory = None
    context.engine.memory = None

    result = await dispatch_command(
        ParsedCommand(name="memory", arguments=()),
        context,
    )
    assert result.message == "Structured memory is not available."


async def test_dispatch_memory_crud(tmp_path):
    from sensai.memory.manager import SqliteMemoryManager

    context = _context()
    mem = SqliteMemoryManager(tmp_path / "cmd_mem.db")
    context.structured_memory = mem

    # Empty list
    res = await dispatch_command(ParsedCommand(name="memory", arguments=()), context)
    assert res.message == "No memories stored."

    # Set fact
    res_set = await dispatch_command(
        ParsedCommand(name="memory", arguments=("set", "user", "lang", "Python 3.11")),
        context,
    )
    assert "Saved: user.lang = Python 3.11" in (res_set.message or "")

    # Get fact
    res_get = await dispatch_command(
        ParsedCommand(name="memory", arguments=("get", "user", "lang")),
        context,
    )
    assert res_get.message == "user.lang = Python 3.11"

    # List facts
    res_list = await dispatch_command(
        ParsedCommand(name="memory", arguments=("list",)),
        context,
    )
    assert "• user.lang = Python 3.11" in (res_list.message or "")

    # Search facts
    res_search = await dispatch_command(
        ParsedCommand(name="memory", arguments=("search", "python")),
        context,
    )
    assert "• user.lang = Python 3.11" in (res_search.message or "")

    # Delete fact
    res_del = await dispatch_command(
        ParsedCommand(name="memory", arguments=("delete", "user", "lang")),
        context,
    )
    assert "Deleted memory: user.lang" in (res_del.message or "")

    # Clear facts
    mem.store_fact("e", "k", "v")
    res_clear = await dispatch_command(
        ParsedCommand(name="memory", arguments=("clear",)),
        context,
    )
    assert res_clear.message == "All structured memories cleared."
    assert mem.list_facts() == []


async def test_dispatch_memory_usage_and_errors(tmp_path):
    from sensai.memory.manager import SqliteMemoryManager

    context = _context()
    mem = SqliteMemoryManager(tmp_path / "cmd_mem_err.db")
    context.structured_memory = mem

    # Unknown subcommand
    res_bad = await dispatch_command(
        ParsedCommand(name="memory", arguments=("unknown",)),
        context,
    )
    assert "Usage: /memory [list" in (res_bad.message or "")

    # Get bad arity
    res_get_bad = await dispatch_command(
        ParsedCommand(name="memory", arguments=("get", "user")),
        context,
    )
    assert res_get_bad.message == "Usage: /memory get <entity> <key>"

    # Get not found
    res_get_miss = await dispatch_command(
        ParsedCommand(name="memory", arguments=("get", "user", "editor")),
        context,
    )
    assert res_get_miss.message == "Memory not found: user.editor"

    # Set bad arity
    res_set_bad = await dispatch_command(
        ParsedCommand(name="memory", arguments=("set", "user")),
        context,
    )
    assert res_set_bad.message == "Usage: /memory set <entity> <key> <value>"

    # Delete bad arity
    res_del_bad = await dispatch_command(
        ParsedCommand(name="memory", arguments=("delete", "user")),
        context,
    )
    assert res_del_bad.message == "Usage: /memory delete <entity> <key>"

    # Delete not found
    res_del_miss = await dispatch_command(
        ParsedCommand(name="memory", arguments=("delete", "user", "editor")),
        context,
    )
    assert res_del_miss.message == "Memory not found: user.editor"

    # Search bad arity
    res_search_bad = await dispatch_command(
        ParsedCommand(name="memory", arguments=("search",)),
        context,
    )
    assert res_search_bad.message == "Usage: /memory search <query>"

    # Search no match
    res_search_none = await dispatch_command(
        ParsedCommand(name="memory", arguments=("search", "nonexistent")),
        context,
    )
    assert res_search_none.message == "No memories matching 'nonexistent'."

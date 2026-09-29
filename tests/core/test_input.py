from sensai.core.commands import CommandContext
from sensai.core.config import AppConfig
from sensai.core.engine import ChatEngine
from sensai.core.input import process_input
from sensai.domain.models import Conversation
from sensai.providers import get_provider
from sensai.providers.mock import MockLLMProvider
from sensai.tools.registry import ToolRegistry, build_default_registry


class RecordingStore:
    def __init__(self):
        self.saved = []

    async def save(self, conversation):
        self.saved.append(conversation.model_copy(deep=True))

    async def load(self, conversation_id):
        return None


def _context():
    store = RecordingStore()
    registry = ToolRegistry()
    context = CommandContext(
        config=AppConfig(provider="mock"),
        engine=ChatEngine(
            MockLLMProvider(default_response="answer", simulated_delay=0),
            Conversation(),
            registry,
        ),
        provider_factory=get_provider,
        tool_registry=registry,
        tool_registry_factory=build_default_registry,
        memory_store=store,
    )
    return context, store


async def test_chat_input_streams_and_saves_conversation():
    context, store = _context()
    received = []

    async def render(events):
        received.extend([event async for event in events])

    result = await process_input(context, "hello", render)

    assert result.message is None
    assert received
    assert [message.content for message in store.saved[0].messages] == [
        "hello",
        "answer",
    ]


async def test_slash_command_does_not_call_chat_renderer():
    context, store = _context()
    context.engine.conversation.add_message("user", "old")

    async def render(events):
        raise AssertionError("slash command should not stream chat")

    result = await process_input(context, "/clear", render)

    assert result.message == "Conversation cleared."
    assert context.engine.conversation.messages == []
    assert len(store.saved) == 1
    assert store.saved[0].messages == []


async def test_exit_command_returns_exit_signal():
    context, _ = _context()

    async def render(events):
        raise AssertionError("exit should not stream chat")

    result = await process_input(context, "/exit", render)

    assert result.should_exit is True

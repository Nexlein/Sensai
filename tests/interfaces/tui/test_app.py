from sensai.core.commands import CommandContext
from sensai.core.config import AppConfig
from sensai.core.engine import ChatEngine
from sensai.domain.models import Conversation
from sensai.interfaces.tui.app import run_tui
from sensai.providers import get_provider
from sensai.providers.mock import MockLLMProvider
from sensai.tools.registry import ToolRegistry, build_default_registry


async def test_tui_uses_shared_input_handler_and_persists_reply(monkeypatch):
    saved = []

    class FakeMemoryStore:
        async def save(self, conversation):
            saved.append(conversation.model_copy(deep=True))

        async def load(self, conversation_id):
            return None

    class FakeChatApp:
        def __init__(self, process):
            self.process = process

        async def run_async(self):
            async def render(events):
                self.events = [event async for event in events]

            self.chat_result = await self.process("hello", render)
            self.clear_result = await self.process("/clear", render)

    app = None

    def make_app(process):
        nonlocal app
        app = FakeChatApp(process)
        return app

    monkeypatch.setattr("sensai.interfaces.tui.app.ChatApp", make_app)
    registry = ToolRegistry()
    engine = ChatEngine(
        MockLLMProvider(default_response="answer", simulated_delay=0),
        Conversation(),
        registry,
    )
    context = CommandContext(
        config=AppConfig(interface="tui"),
        engine=engine,
        provider_factory=get_provider,
        tool_registry=registry,
        tool_registry_factory=build_default_registry,
        memory_store=FakeMemoryStore(),
    )

    await run_tui(context)

    assert app is not None
    assert app.events
    assert app.chat_result.message is None
    assert app.clear_result.message == "Conversation cleared."
    assert [message.content for message in saved[0].messages] == ["hello", "answer"]
    assert context.engine.conversation.messages == []
    assert saved[-1].messages == []

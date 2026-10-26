import asyncio

import pytest
from fastapi.testclient import TestClient

from sensai.core.budget import BudgetConfig, ContextBudget
from sensai.core.commands import CommandContext
from sensai.core.config import AppConfig
from sensai.core.engine import ChatEngine
from sensai.domain.events import TextChunkEvent, ToolCallEvent, UsageEvent
from sensai.domain.models import Conversation, Message
from sensai.interfaces.web.app import build_app
from sensai.providers import get_provider
from sensai.providers.mock import MockLLMProvider
from sensai.tools.registry import ToolRegistry, build_default_registry


class FakeMemoryStore:
    def __init__(self):
        self.saved = []

    async def save(self, conversation):
        self.saved.append(conversation.model_copy(deep=True))

    async def load(self, conversation_id):
        return None


class SensitiveTool:
    name = "danger"
    description = "does something risky"
    requires_confirmation = True

    def __init__(self):
        self.parameters_schema = {"type": "object", "properties": {}}
        self.runs = 0

    async def execute(self, **kwargs):
        self.runs += 1
        return "done"


class ToolThenTextProvider:
    async def chat_stream(self, messages, tools=None, think=None):
        if messages[-1].role == "tool":
            yield TextChunkEvent(content="finished")
        else:
            yield ToolCallEvent(tool_name="danger", arguments={"path": "a"})


class SlowProvider:
    async def chat_stream(self, messages, tools=None, think=None):
        yield TextChunkEvent(content="start")
        await asyncio.sleep(30)
        yield TextChunkEvent(content="never")


class FailingProvider:
    async def chat_stream(self, messages, tools=None, think=None):
        raise RuntimeError("boom")
        yield


def _context(provider, registry=None, conversation=None):
    registry = registry or ToolRegistry()
    conversation = conversation or Conversation()
    return CommandContext(
        config=AppConfig(interface="web"),
        engine=ChatEngine(provider, conversation, registry),
        provider_factory=get_provider,
        tool_registry=registry,
        tool_registry_factory=build_default_registry,
        memory_store=FakeMemoryStore(),
    )


def _until(ws, *types):
    """Collect messages up to and including the first one of the given types."""
    seen = []
    while True:
        data = ws.receive_json()
        seen.append(data)
        if data["type"] in types:
            return seen


def test_index_serves_the_chat_page():
    client = TestClient(build_app(_context(MockLLMProvider())))

    response = client.get("/")

    assert response.status_code == 200
    assert "WebSocket" in response.text


def test_message_streams_chunks_then_done_and_saves_the_conversation():
    context = _context(MockLLMProvider("hello there", simulated_delay=0))
    client = TestClient(build_app(context))

    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json() == {"type": "history", "messages": []}
        ws.send_json({"type": "message", "text": "hi"})
        seen = _until(ws, "done")

    chunks = [m["content"] for m in seen if m["type"] == "text_chunk"]
    assert "".join(chunks) == "hello there"
    assert len(chunks) > 1
    assert [m.content for m in context.memory_store.saved[-1].messages] == [
        "hi",
        "hello there",
    ]


def test_usage_is_sent_once_per_turn_not_per_chunk():
    context = _context(MockLLMProvider("one two three four", simulated_delay=0))
    context.engine.budget = ContextBudget(BudgetConfig(max_tokens=1000), None)
    client = TestClient(build_app(context))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "hi"})
        seen = _until(ws, "done")

    assert len([m for m in seen if m["type"] == "text_chunk"]) > 1
    assert len([m for m in seen if m["type"] == "usage"]) == 1
    assert seen[-2]["type"] == "usage"


class CountingProvider:
    async def chat_stream(self, messages, tools=None, **options):
        yield TextChunkEvent(content="hello")
        yield UsageEvent(prompt_tokens=42, reply_tokens=3)


def test_real_counters_are_sent_after_the_budget_line():
    context = _context(CountingProvider())
    context.engine.budget = ContextBudget(BudgetConfig(max_tokens=1000), None)
    client = TestClient(build_app(context))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "hi"})
        seen = _until(ws, "done")

    usage = [m["message"] for m in seen if m["type"] == "usage"]
    assert len(usage) == 2
    assert usage[1] == "prompt 42 tok · reply 3 tok"


def test_history_replays_the_resumed_conversation():
    conversation = Conversation(
        messages=[
            Message(id="1", role="system", content="rules"),
            Message(id="2", role="user", content="earlier"),
            Message(id="3", role="assistant", content="answer"),
            Message(id="4", role="tool", content="tool output"),
        ]
    )
    client = TestClient(
        build_app(_context(MockLLMProvider(), conversation=conversation))
    )

    with client.websocket_connect("/ws") as ws:
        history = ws.receive_json()

    assert history["messages"] == [
        {"role": "user", "content": "earlier"},
        {"role": "assistant", "content": "answer"},
    ]


def test_slash_command_goes_through_the_shared_handler():
    client = TestClient(build_app(_context(MockLLMProvider())))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "/clear"})
        seen = _until(ws, "done")

    assert {"type": "notice", "message": "Conversation cleared."} in seen


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_message_reports_an_error_and_keeps_the_socket_usable(text):
    client = TestClient(build_app(_context(MockLLMProvider("ok", simulated_delay=0))))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": text})
        seen = _until(ws, "done")
        assert seen[0]["type"] == "error"
        assert "Empty input" in seen[0]["message"]

        ws.send_json({"type": "message", "text": "again"})
        assert any(m["type"] == "text_chunk" for m in _until(ws, "done"))


def test_provider_failure_is_one_error_line_not_a_crash():
    client = TestClient(build_app(_context(FailingProvider())))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "hi"})
        seen = _until(ws, "done")

    assert seen[0]["type"] == "error"
    assert seen[0]["message"].startswith("Model unavailable")


@pytest.mark.parametrize("approved, runs", [(True, 1), (False, 0)])
def test_tool_confirmation_round_trip(approved, runs):
    tool = SensitiveTool()
    registry = ToolRegistry()
    registry.register(tool)
    client = TestClient(build_app(_context(ToolThenTextProvider(), registry)))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "go"})
        ask = _until(ws, "confirm")[-1]
        assert ask["title"] == "Allow danger?"
        assert ask["details"] == [["path", "a"]]
        ws.send_json({"type": "confirm", "approved": approved})
        _until(ws, "done")

    assert tool.runs == runs


def test_stop_cancels_the_turn_and_drops_the_unanswered_message():
    context = _context(SlowProvider())
    client = TestClient(build_app(context))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "slow"})
        _until(ws, "text_chunk")
        ws.send_json({"type": "stop"})
        seen = _until(ws, "done")

    assert {"type": "notice", "message": "Stopped."} in seen
    assert context.engine.conversation.messages == []


def test_second_message_during_a_turn_is_refused():
    client = TestClient(build_app(_context(SlowProvider())))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "one"})
        _until(ws, "text_chunk")
        ws.send_json({"type": "message", "text": "two"})
        refusal = ws.receive_json()
        ws.send_json({"type": "stop"})
        _until(ws, "done")

    assert refusal["type"] == "error"
    assert "already in progress" in refusal["message"]


def test_unknown_or_malformed_payloads_are_ignored():
    client = TestClient(build_app(_context(MockLLMProvider("ok", simulated_delay=0))))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "confirm", "approved": True})  # nothing pending
        ws.send_json({"type": "nonsense"})
        ws.send_json(["not", "a", "dict"])
        ws.send_json({"type": "message", "text": "hi"})
        assert any(m["type"] == "text_chunk" for m in _until(ws, "done"))


def test_guardrail_masking_reaches_the_page_as_a_notice():
    from sensai.eval.guardrails import RegexGuardrail

    context = _context(MockLLMProvider(default_response="noted", simulated_delay=0))
    context.engine.guardrail = RegexGuardrail()
    client = TestClient(build_app(context))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "Rappelle le 06 12 34 56 78"})
        seen = _until(ws, "done")

    notices = [m["message"] for m in seen if m["type"] == "notice"]
    assert notices and "phone" in notices[0]
    stored = context.engine.conversation.messages[0].content
    assert "06 12 34 56 78" not in stored


def test_disconnecting_mid_turn_cancels_it_and_drops_the_unanswered_message():
    context = _context(SlowProvider())
    client = TestClient(build_app(context))

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "slow"})
        _until(ws, "text_chunk")

    assert context.engine.conversation.messages == []

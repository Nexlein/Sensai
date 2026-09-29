import pytest
from pydantic import ValidationError

from sensai.domain.events import (
    Event,
    GuardrailEvent,
    TextChunkEvent,
    ToolCallEvent,
)


def test_text_chunk_event_type_and_content():
    event = TextChunkEvent(content="hello")
    assert event.type == "text_chunk"
    assert event.content == "hello"
    assert event.timestamp is not None


def test_tool_call_event_type_and_fields():
    event = ToolCallEvent(tool_name="search", arguments={"q": "x"})
    assert event.type == "tool_call"
    assert event.tool_name == "search"
    assert event.arguments == {"q": "x"}


def test_events_are_event_instances():
    assert isinstance(TextChunkEvent(content="hi"), Event)
    assert isinstance(ToolCallEvent(tool_name="x", arguments={}), Event)


def test_guardrail_event_type_and_fields():
    event = GuardrailEvent(stage="input", action="block", reason="prompt injection")
    assert event.type == "guardrail"
    assert event.stage == "input"
    assert event.action == "block"
    assert event.reason == "prompt injection"
    assert isinstance(event, Event)


def test_guardrail_event_rejects_unknown_stage_or_action():
    with pytest.raises(ValidationError):
        GuardrailEvent(stage="somewhere", action="block", reason="x")
    with pytest.raises(ValidationError):
        GuardrailEvent(stage="input", action="explode", reason="x")

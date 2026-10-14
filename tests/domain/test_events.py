import pytest
from pydantic import ValidationError

from sensai.domain.events import (
    BudgetEvent,
    Event,
    GuardrailEvent,
    MaxStepsEvent,
    StepEvent,
    TextChunkEvent,
    ThoughtEvent,
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


def test_budget_event_type_and_fields():
    event = BudgetEvent(used=10, max_tokens=100)
    assert event.type == "budget"
    assert (event.used, event.max_tokens) == (10, 100)


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


def test_thought_event_defaults_to_text_source():
    event = ThoughtEvent(content="I need the file first")
    assert event.type == "thought"
    assert event.content == "I need the file first"
    assert event.source == "text"
    assert isinstance(event, Event)


def test_thought_event_rejects_unknown_source():
    with pytest.raises(ValidationError):
        ThoughtEvent(content="x", source="guess")


def test_step_event_type_and_fields():
    event = StepEvent(index=2, max_steps=5)
    assert event.type == "step"
    assert (event.index, event.max_steps) == (2, 5)
    assert isinstance(event, Event)


def test_max_steps_event_type_and_fields():
    event = MaxStepsEvent(max_steps=5)
    assert event.type == "max_steps"
    assert event.max_steps == 5
    assert isinstance(event, Event)

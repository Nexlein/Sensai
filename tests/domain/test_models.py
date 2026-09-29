import pytest
from pydantic import ValidationError

from sensai.domain.models import (
    Conversation,
    GuardrailFinding,
    GuardrailVerdict,
    Message,
    Persona,
    ToolCall,
)


def test_message_defaults_id_and_timestamp():
    msg = Message(role="user", content="hi")
    assert msg.id
    assert msg.timestamp is not None
    assert msg.tool_calls is None


def test_message_with_tool_calls():
    tc = ToolCall(name="search", arguments={"q": "x"})
    msg = Message(role="assistant", content="", tool_calls=[tc])
    assert msg.tool_calls == [tc]
    assert msg.tool_calls[0].name == "search"


def test_tool_call_defaults_id():
    tc = ToolCall(name="search", arguments={"q": "x"})
    assert tc.id
    assert tc.arguments == {"q": "x"}


def test_conversation_starts_empty():
    convo = Conversation()
    assert convo.messages == []
    assert convo.id
    assert convo.created_at is not None


def test_conversation_add_message_appends_and_returns():
    convo = Conversation()
    msg = convo.add_message(role="user", content="hello")
    assert convo.messages == [msg]
    assert msg.role == "user"
    assert msg.content == "hello"


def test_conversation_add_message_updates_updated_at():
    convo = Conversation()
    original_updated_at = convo.updated_at
    convo.add_message(role="user", content="hello")
    assert convo.updated_at >= original_updated_at


def test_conversation_add_message_with_tool_calls():
    convo = Conversation()
    tc = ToolCall(name="search", arguments={})
    msg = convo.add_message(role="assistant", content="", tool_calls=[tc])
    assert msg.tool_calls == [tc]


def test_persona_fields():
    persona = Persona(
        id="p1",
        name="Assistant",
        description="A helpful assistant",
        system_instruction="Be helpful.",
    )
    assert persona.id == "p1"
    assert persona.name == "Assistant"


def test_guardrail_verdict_defaults_to_no_findings():
    verdict = GuardrailVerdict(action="allow", text="hello")
    assert verdict.findings == []


def test_guardrail_verdict_findings_are_not_shared_between_instances():
    a = GuardrailVerdict(action="allow", text="a")
    b = GuardrailVerdict(action="allow", text="b")
    a.findings.append(GuardrailFinding(rule="email", category="pii"))
    assert b.findings == []


def test_guardrail_verdict_rejects_unknown_action():
    with pytest.raises(ValidationError):
        GuardrailVerdict(action="explode", text="x")


def test_guardrail_finding_holds_rule_and_category_only():
    finding = GuardrailFinding(rule="iban", category="pii")
    assert finding.model_dump() == {"rule": "iban", "category": "pii"}

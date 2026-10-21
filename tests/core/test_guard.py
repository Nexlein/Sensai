"""Guardrail events and their reasons."""

from sensai.core.guard import guardrail_event, reason
from sensai.domain.models import GuardrailFinding


def test_reason_groups_rules_by_category_without_duplicates():
    findings = [
        GuardrailFinding(rule="ignore_instructions", category="injection"),
        GuardrailFinding(rule="email", category="pii"),
        GuardrailFinding(rule="phone", category="pii"),
        GuardrailFinding(rule="email", category="pii"),
    ]

    assert reason(findings) == "injection: ignore_instructions; pii: email, phone"


def test_reason_is_empty_without_findings():
    assert reason([]) == ""


def test_guardrail_event_carries_stage_action_and_reason():
    event = guardrail_event(
        "tool", "redact", [GuardrailFinding(rule="iban", category="pii")]
    )

    assert (event.stage, event.action, event.reason) == ("tool", "redact", "pii: iban")

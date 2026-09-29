import pytest

from sensai.domain.events import GuardrailEvent
from sensai.interfaces.notices import guardrail_notice


@pytest.mark.parametrize("stage", ["input", "output", "tool"])
@pytest.mark.parametrize("action", ["block", "redact", "flag", "allow"])
def test_every_stage_and_action_produces_a_notice_with_the_reason(stage, action):
    event = GuardrailEvent(stage=stage, action=action, reason="pii: email")

    notice = guardrail_notice(event)

    assert "pii: email" in notice
    assert notice.endswith(".")


def test_blocked_input_says_nothing_was_sent():
    event = GuardrailEvent(
        stage="input", action="block", reason="injection: ignore_instructions"
    )

    assert "Nothing was sent to the model" in guardrail_notice(event)


def test_notices_differ_by_stage_and_action():
    notices = {
        guardrail_notice(GuardrailEvent(stage=stage, action=action, reason="r"))
        for stage in ("input", "output", "tool")
        for action in ("block", "redact")
    }

    assert len(notices) == 6


def test_unlisted_combination_falls_back_to_a_generic_notice():
    event = GuardrailEvent(stage="output", action="flag", reason="pii: iban")

    assert guardrail_notice(event) == "Guardrail flag on output (pii: iban)."

import httpx
import pytest

from sensai.domain.errors import ProviderError
from sensai.domain.events import GuardrailEvent
from sensai.interfaces.notices import error_text, guardrail_notice


def _provider_error(cause: Exception) -> ProviderError:
    exc = ProviderError("provider request failed")
    exc.__cause__ = cause
    return exc


@pytest.mark.parametrize(
    ("cause", "expected"),
    [
        (httpx.ConnectError("refused"), "Connection failed"),
        (httpx.ConnectTimeout("slow"), "timed out"),
        (httpx.ReadTimeout("slow"), "timed out"),
        (httpx.RemoteProtocolError("closed"), "Connection lost"),
        (httpx.ReadError("reset"), "Connection lost"),
        (RuntimeError("HTTP Provider Error [404]: no model"), "Model unavailable"),
    ],
)
def test_error_text_names_the_failure_in_one_line(cause, expected):
    text = error_text(_provider_error(cause))

    assert expected in text
    assert "\n" not in text
    assert "Traceback" not in text


def test_error_text_shows_the_reason_a_provider_raised_itself():
    text = error_text(ProviderError("Groq error [400]: bad tool message"))

    assert text == "Model unavailable — Groq error [400]: bad tool message"


def test_error_text_hides_the_engine_wrapper_message():
    text = error_text(ProviderError("provider request failed"))

    assert "provider request failed" not in text


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

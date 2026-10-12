"""User-facing wording shared by every frontend."""

import httpx

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import GuardrailEvent

ENGINE_WRAPPER_MESSAGE = "provider request failed"

_NOTICES = {
    ("input", "block"): "Message blocked ({reason}). Nothing was sent to the model.",
    ("input", "redact"): "Personal data in your message was masked ({reason}).",
    ("input", "flag"): "Message flagged ({reason}), sent as written.",
    ("output", "block"): "Reply withheld ({reason}).",
    ("output", "redact"): "Personal data in the reply was masked ({reason}).",
    ("tool", "block"): "Tool result withheld ({reason}).",
    ("tool", "redact"): "Personal data in a tool result was masked ({reason}).",
}


def guardrail_notice(event: GuardrailEvent) -> str:
    """One line telling the user what a guardrail did, and which rules fired."""
    template = _NOTICES.get(
        (event.stage, event.action),
        "Guardrail {action} on {stage} ({reason}).",
    )
    return template.format(action=event.action, stage=event.stage, reason=event.reason)


def error_text(exc: Exception) -> str:
    """One line for a failed turn: what went wrong, never a traceback."""
    if isinstance(exc, EmptyInputError):
        return "Empty input — please enter a message before sending."
    if isinstance(exc, ProviderError):
        cause = exc.__cause__
        if isinstance(cause, httpx.ConnectError):
            return "Connection failed — could not connect to the model server."
        if isinstance(cause, httpx.TimeoutException):
            return "Model server timed out — it did not accept the request in time."
        if isinstance(cause, httpx.TransportError):
            return "Connection lost — the model server closed the connection."
        # Providers that raise ProviderError themselves (Groq) already wrote a
        # readable reason; the engine's wrapper message carries none.
        if not cause and (detail := str(exc)) and detail != ENGINE_WRAPPER_MESSAGE:
            return f"Model unavailable — {detail}"
        return "Model unavailable — the model is unavailable or returned an error."
    return f"Unexpected error — {exc}"

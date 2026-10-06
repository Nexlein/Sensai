"""User-facing wording shared by every frontend."""

from sensai.domain.events import GuardrailEvent

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

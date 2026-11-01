from typing import Literal

from sensai.domain.events import GuardrailEvent
from sensai.domain.models import GuardrailAction, GuardrailFinding


def reason(findings: list[GuardrailFinding]) -> str:
    """Which rules fired, e.g. "injection: ignore_instructions; pii: email".

    Rule names only: the matched text is never put in an event or a log.
    """
    rules_by_category: dict[str, list[str]] = {}
    for finding in findings:
        rules_by_category.setdefault(finding.category, []).append(finding.rule)
    return "; ".join(
        f"{category}: {', '.join(dict.fromkeys(rules))}"
        for category, rules in rules_by_category.items()
    )


def guardrail_event(
    stage: Literal["input", "output", "tool"],
    action: GuardrailAction,
    findings: list[GuardrailFinding],
) -> GuardrailEvent:
    """Build the event that tells the UI a guardrail acted at `stage`."""
    return GuardrailEvent(stage=stage, action=action, reason=reason(findings))

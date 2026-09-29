"""Deterministic Guardrail: PII redaction/refusal plus injection heuristics."""

from dataclasses import dataclass, field
from typing import Literal

from sensai.domain.models import GuardrailAction, GuardrailFinding, GuardrailVerdict
from sensai.eval.guardrails.injection import find_injection
from sensai.eval.guardrails.pii import redact_pii
from sensai.eval.guardrails.pii_rules import PII_RULES
from sensai.eval.guardrails.pii_types import PiiRule
from sensai.eval.guardrails.stream import PiiOutputStream


@dataclass(frozen=True)
class RegexGuardrail:
    """Deterministic Guardrail: PII redaction/refusal plus injection heuristics."""

    injection_action: Literal["block", "flag"] = "block"
    pii_action: Literal["redact", "block"] = "redact"
    pii_rules: tuple[PiiRule, ...] = field(default=PII_RULES, repr=False)

    async def filter_input(self, text: str) -> GuardrailVerdict:
        injection = find_injection(text)
        redacted, matches = redact_pii(text, self.pii_rules)
        pii = [GuardrailFinding(rule=m.rule, category="pii") for m in matches]
        findings = [*injection, *pii]

        # Precedence: block > redact > flag > allow.
        action: GuardrailAction
        refused = bool(injection) and self.injection_action == "block"
        refused = refused or (bool(matches) and self.pii_action == "block")
        if refused:
            action = "block"
        elif matches:
            action = "redact"
        elif injection:
            action = "flag"
        else:
            action = "allow"
        return GuardrailVerdict(
            action=action,
            text=redacted if action == "redact" else text,
            findings=findings,
        )

    async def filter_output(self, text: str) -> GuardrailVerdict:
        redacted, matches = redact_pii(text, self.pii_rules)
        if not matches:
            return GuardrailVerdict(action="allow", text=text)
        findings = [GuardrailFinding(rule=m.rule, category="pii") for m in matches]
        if self.pii_action == "block":
            return GuardrailVerdict(action="block", text=text, findings=findings)
        return GuardrailVerdict(action="redact", text=redacted, findings=findings)

    def new_output_stream(self) -> PiiOutputStream:
        return PiiOutputStream(self.pii_action, self.pii_rules)

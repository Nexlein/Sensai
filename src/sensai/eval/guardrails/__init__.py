"""Privacy/content guardrails (EV2): deterministic PII and injection detectors.

Pure functions only: no I/O, no engine coupling. PII detection is regex plus a
checksum validator where the format has one, so a random long number that
merely looks like a card or IBAN is left alone.
"""

from sensai.eval.guardrails.checksums import iban_valid, luhn_valid, nir_valid
from sensai.eval.guardrails.guardrail import RegexGuardrail
from sensai.eval.guardrails.injection import INJECTION_RULES, find_injection
from sensai.eval.guardrails.pii import find_pii, redact_pii
from sensai.eval.guardrails.pii_rules import PII_RULES
from sensai.eval.guardrails.pii_types import PiiMatch, PiiRule
from sensai.eval.guardrails.stream import (
    MAX_EMAIL,
    MAX_SPACED_PII,
    REFUSAL_TEXT,
    PiiOutputStream,
)

__all__ = [
    "INJECTION_RULES",
    "MAX_EMAIL",
    "MAX_SPACED_PII",
    "PII_RULES",
    "REFUSAL_TEXT",
    "PiiMatch",
    "PiiOutputStream",
    "PiiRule",
    "RegexGuardrail",
    "find_injection",
    "find_pii",
    "iban_valid",
    "luhn_valid",
    "nir_valid",
    "redact_pii",
]

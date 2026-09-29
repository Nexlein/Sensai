"""Regex rules for PII detection, in priority order."""

import re

from sensai.eval.guardrails.checksums import (
    card_span,
    card_valid,
    iban_valid,
    nir_valid,
)
from sensai.eval.guardrails.pii_types import PiiRule


def _ascii_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a PII pattern where only ASCII letters/digits are word characters.

    With the default Unicode semantics a word boundary is not found between a CJK
    character and the PII next to it ("邮箱john@example.com谢谢"), so the value
    would go through unmasked in languages that do not put spaces between words.
    """
    return re.compile(pattern, re.ASCII)


# Order is priority: when two rules overlap, the earlier rule keeps the span.
# Structured + checksummed formats go first, loose ones (phone) last.
# Every quantifier is bounded (RFC 5321 limits for email): an unbounded `+` makes
# find_pii quadratic on long runs like "1-1-1-...", since \b matches everywhere.
# The email rule has no leading \b so an over-long local part is still redacted.
PII_RULES: tuple[PiiRule, ...] = (
    PiiRule(
        name="iban",
        pattern=_ascii_pattern(
            r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"
        ),
        replacement="[IBAN]",
        validator=iban_valid,
    ),
    PiiRule(
        name="ssn",
        pattern=_ascii_pattern(
            r"\b[12] ?\d{2} ?(?:0[1-9]|1[0-2]|[2-9]\d) ?(?:\d{2}|2[AB]) ?\d{3} ?\d{3} ?\d{2}\b"
        ),
        replacement="[SSN]",
        validator=nir_valid,
    ),
    PiiRule(
        name="credit_card",
        pattern=_ascii_pattern(r"\b(?:\d[ -]?){12,18}\d\b"),
        replacement="[CARD]",
        validator=card_valid,
        recover=card_span,
    ),
    PiiRule(
        name="email",
        pattern=_ascii_pattern(
            r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+\b"
        ),
        replacement="[EMAIL]",
    ),
    PiiRule(
        name="phone",
        pattern=_ascii_pattern(
            r"(?<![\w+])(?:"
            r"(?:\+|00)33[ .-]?[1-9](?:[ .-]?\d{2}){4}"  # French, international form
            r"|0[1-9](?:[ .-]?\d{2}){4}"  # French, national form
            r"|\+\d{1,3}(?:[ .-]?\d{2,4}){2,4}"  # other international numbers
            r")(?!\d)"
        ),
        replacement="[PHONE]",
    ),
)

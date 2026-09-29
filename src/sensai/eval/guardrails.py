"""Deterministic detectors for the privacy/content guardrails (EV2).

Pure functions only: no I/O, no engine coupling. PII detection is regex plus a
checksum validator where the format has one, so a random long number that
merely looks like a card or IBAN is left alone.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from sensai.domain.models import GuardrailFinding


def luhn_valid(number: str) -> bool:
    """Luhn checksum over a digit string (credit/debit cards)."""
    if not number.isdigit():
        return False
    total = 0
    for index, char in enumerate(reversed(number)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def iban_valid(iban: str) -> bool:
    """ISO 13616 mod-97 check. Length is bounded but not checked per country."""
    compact = iban.replace(" ", "").upper()
    if not 15 <= len(compact) <= 34 or not compact.isalnum():
        return False
    rearranged = compact[4:] + compact[:4]
    # Letters map to 10..35, digits stay as they are (base 36 does exactly that).
    numeric = "".join(str(int(char, 36)) for char in rearranged)
    return int(numeric) % 97 == 1


def nir_valid(nir: str) -> bool:
    """French social security number (NIR): 13 digits + 2-digit key.

    key = 97 - (first 13 digits mod 97). Corsican departments 2A/2B are
    computed as 19/18.
    """
    compact = nir.replace(" ", "").upper()
    if len(compact) != 15:
        return False
    body, key = compact[:13], compact[13:]
    body = body[:5] + body[5:7].replace("2A", "19").replace("2B", "18") + body[7:]
    if not body.isdigit() or not key.isdigit():
        return False
    return 97 - int(body) % 97 == int(key)


@dataclass(frozen=True)
class PiiRule:
    name: str
    pattern: re.Pattern[str]
    replacement: str
    validator: Callable[[str], bool] | None = None


@dataclass(frozen=True)
class PiiMatch:
    rule: str
    start: int
    end: int
    replacement: str


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def _card_valid(value: str) -> bool:
    digits = _digits_only(value)
    return 13 <= len(digits) <= 19 and luhn_valid(digits)


# Order is priority: when two rules overlap, the earlier rule keeps the span.
# Structured + checksummed formats go first, loose ones (phone) last.
# Every quantifier is bounded (RFC 5321 limits for email): an unbounded `+` makes
# find_pii quadratic on long runs like "1-1-1-...", since \b matches everywhere.
# The email rule has no leading \b so an over-long local part is still redacted.
PII_RULES: tuple[PiiRule, ...] = (
    PiiRule(
        name="iban",
        pattern=re.compile(
            r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"
        ),
        replacement="[IBAN]",
        validator=iban_valid,
    ),
    PiiRule(
        name="ssn",
        pattern=re.compile(
            r"\b[12] ?\d{2} ?(?:0[1-9]|1[0-2]|[2-9]\d) ?(?:\d{2}|2[AB]) ?\d{3} ?\d{3} ?\d{2}\b"
        ),
        replacement="[SSN]",
        validator=nir_valid,
    ),
    PiiRule(
        name="credit_card",
        pattern=re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
        replacement="[CARD]",
        validator=_card_valid,
    ),
    PiiRule(
        name="email",
        pattern=re.compile(
            r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+\b"
        ),
        replacement="[EMAIL]",
    ),
    PiiRule(
        name="phone",
        pattern=re.compile(
            r"(?<![\w+])(?:"
            r"(?:\+|00)33[ .-]?[1-9](?:[ .-]?\d{2}){4}"  # French, international form
            r"|0[1-9](?:[ .-]?\d{2}){4}"  # French, national form
            r"|\+\d{1,3}(?:[ .-]?\d{2,4}){2,4}"  # other international numbers
            r")(?!\d)"
        ),
        replacement="[PHONE]",
    ),
)


def find_pii(text: str, rules: tuple[PiiRule, ...] = PII_RULES) -> list[PiiMatch]:
    """Return non-overlapping PII matches sorted by position."""
    taken: list[PiiMatch] = []
    for rule in rules:
        for match in rule.pattern.finditer(text):
            if rule.validator is not None and not rule.validator(match.group()):
                continue
            start, end = match.span()
            if any(start < t.end and t.start < end for t in taken):
                continue
            taken.append(PiiMatch(rule.name, start, end, rule.replacement))
    return sorted(taken, key=lambda m: m.start)


def redact_pii(
    text: str, rules: tuple[PiiRule, ...] = PII_RULES
) -> tuple[str, list[PiiMatch]]:
    """Replace every PII match by its token. Returns the new text and the matches."""
    matches = find_pii(text, rules)
    pieces: list[str] = []
    cursor = 0
    for match in matches:
        pieces.append(text[cursor : match.start])
        pieces.append(match.replacement)
        cursor = match.end
    pieces.append(text[cursor:])
    return "".join(pieces), matches


_FLAGS = re.IGNORECASE | re.DOTALL

INJECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(
            r"\b(?:ignore|disregard|forget|override)\b.{0,30}"
            r"\b(?:previous|prior|above|earlier|all|any|your|the)\b.{0,30}"
            r"\b(?:instructions?|rules?|prompts?|guidelines?)\b",
            _FLAGS,
        ),
    ),
    (
        "ignore_instructions_fr",
        re.compile(
            r"\b(?:ignore[rsz]?|oublie[rsz]?)\b.{0,40}"
            r"\b(?:instructions?|consignes?|r[èe]gles?)\b",
            _FLAGS,
        ),
    ),
    (
        "reveal_prompt",
        re.compile(
            r"\b(?:reveal|show|print|repeat|display|leak|output|tell me)\b.{0,30}"
            r"\b(?:system|initial|hidden|original)\s+(?:prompt|instructions?|message)\b",
            _FLAGS,
        ),
    ),
    (
        "jailbreak_persona",
        re.compile(
            r"\bdo anything now\b|\bdeveloper mode\b"
            r"|\b(?:you are now|act as|pretend to be)\b.{0,40}"
            r"\b(?:DAN|unrestricted|without (?:any )?(?:rules|restrictions|filters))\b",
            _FLAGS,
        ),
    ),
)


def find_injection(text: str) -> list[GuardrailFinding]:
    """Flag prompt-injection / jailbreak phrasings. Heuristic, easy to bypass."""
    return [
        GuardrailFinding(rule=name, category="injection")
        for name, pattern in INJECTION_RULES
        if pattern.search(text)
    ]

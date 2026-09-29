"""Deterministic detectors for the privacy/content guardrails (EV2).

Pure functions only: no I/O, no engine coupling. PII detection is regex plus a
checksum validator where the format has one, so a random long number that
merely looks like a card or IBAN is left alone.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from sensai.domain.models import GuardrailAction, GuardrailFinding, GuardrailVerdict


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
    # Called with a match that failed `validator`: returns the (start, end) of a
    # valid part inside it, if any.
    recover: Callable[[str], tuple[int, int] | None] | None = None


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


def _card_span(value: str) -> tuple[int, int] | None:
    """Find a valid card inside a longer run of digit groups.

    "4111 1111 1111 1111 123" (card + CVV) is one 19-digit run that fails Luhn,
    yet its first four groups are a card. Candidates are runs of whole groups
    (split on space/hyphen), so digits glued together are never cut apart. The
    longest valid run wins: in "105 4111 1111 1111 1111" the 15 digits
    "105 4111 1111 1111" also pass Luhn by chance, but taking them would leave
    the last "1111" of the real card unmasked.
    """
    groups = [m.span() for m in re.finditer(r"[^ -]+", value)]
    best: tuple[int, tuple[int, int]] | None = None
    for first in range(len(groups)):
        for last in range(first, len(groups)):
            start, end = groups[first][0], groups[last][1]
            if not _card_valid(value[start:end]):
                continue
            digits = len(_digits_only(value[start:end]))
            if best is None or digits > best[0]:
                best = (digits, (start, end))
    return best[1] if best else None


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
        recover=_card_span,
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
            start, end = match.span()
            if rule.validator is not None and not rule.validator(match.group()):
                inner = rule.recover(match.group()) if rule.recover else None
                if inner is None:
                    continue
                start, end = match.start() + inner[0], match.start() + inner[1]
            if any(start < t.end and t.start < end for t in taken):
                continue
            taken.append(PiiMatch(rule.name, start, end, rule.replacement))
    return sorted(taken, key=lambda m: m.start)


def _substitute(text: str, matches: list[PiiMatch], upto: int) -> str:
    """Return text[:upto] with every match that ends at or before `upto` replaced."""
    pieces: list[str] = []
    cursor = 0
    for match in matches:
        if match.end > upto:
            break
        pieces.append(text[cursor : match.start])
        pieces.append(match.replacement)
        cursor = match.end
    pieces.append(text[cursor:upto])
    return "".join(pieces)


def redact_pii(
    text: str, rules: tuple[PiiRule, ...] = PII_RULES
) -> tuple[str, list[PiiMatch]]:
    """Replace every PII match by its token. Returns the new text and the matches."""
    matches = find_pii(text, rules)
    return _substitute(text, matches, len(text)), matches


_FLAGS = re.IGNORECASE | re.DOTALL

INJECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(
            # English
            r"\b(?:ignore|disregard|forget|override)\b.{0,30}"
            r"\b(?:previous|prior|above|earlier|all|any|your|the)\b.{0,30}"
            r"\b(?:instructions?|rules?|prompts?|guidelines?)\b"
            # French
            r"|\b(?:ignore[rsz]?|oublie[rsz]?)\b.{0,40}"
            r"\b(?:instructions?|consignes?|r[èe]gles?)\b",
            _FLAGS,
        ),
    ),
    (
        "reveal_prompt",
        re.compile(
            # "show the system prompt", "print the hidden instructions"
            r"\b(?:reveal|show|print|repeat|display|leak|output|dump|paste|tell me)\b.{0,30}"
            r"\b(?:system|initial|hidden|original|secret)\s+(?:prompt|instructions?|message)\b"
            # "give me your prompt system", "what are your instructions": these
            # verbs are only suspicious when aimed at *your*/*its* prompt.
            r"|\b(?:reveal|show|print|repeat|display|leak|output|dump|paste|share|send"
            r"|tell|give|list|recite|what(?:'s|\s+is|\s+are))\b.{0,30}"
            r"\b(?:your|its)\b.{0,20}\b(?:prompts?|instructions?|programming|directives?)\b"
            # French: "donne-moi ton prompt système", "montre-moi tes instructions"
            r"|\b(?:donne|montre|affiche|r[ée]p[èe]te|envoie|r[ée]v[èe]le|liste)[\w-]*\b.{0,30}"
            r"\b(?:ton|tes|ta|votre|vos)\b.{0,20}\b(?:prompts?|instructions?|consignes?|directives?)\b",
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


REFUSAL_TEXT = "[response withheld: it contained personal data]"

# Streaming hold-back. A match can only be completed by text still to come, so
# the tail of the buffer is kept until it can no longer be part of a match.
# - spaced formats (IBAN <= 34 chars + 8 spaces) never exceed 48 chars;
# - an email has no spaces, so a partial one lives inside the trailing word,
#   and is at most 64 + 1 + 253 chars.
MAX_SPACED_PII = 48
MAX_EMAIL = 320
_WHITESPACE = " \t\r\n"


def _last_whitespace(text: str, before: int) -> int:
    """Index of the last whitespace char strictly before `before`, or -1."""
    return max(text.rfind(ch, 0, before) for ch in _WHITESPACE)


class PiiOutputStream:
    """Redacts (or refuses) PII in a stream of chunks, without splitting matches.

    Each `feed` returns the part of the buffered text that is safe to show; the
    rest stays buffered until later chunks or `flush` settle it.
    """

    def __init__(
        self,
        action: Literal["redact", "block"] = "redact",
        rules: tuple[PiiRule, ...] = PII_RULES,
    ) -> None:
        self._action = action
        self._rules = rules
        self._buffer = ""
        self.refused = False
        self.findings: list[GuardrailFinding] = []

    def feed(self, chunk: str) -> str:
        if self.refused:
            return ""
        self._buffer += chunk
        return self._drain(final=False)

    def flush(self) -> str:
        if self.refused:
            return ""
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> str:
        matches = find_pii(self._buffer, self._rules)
        if matches and self._action == "block":
            return self._refuse(matches[0])

        cut = len(self._buffer) if final else self._cut_point(matches)
        if cut <= 0:
            return ""
        emitted = _substitute(self._buffer, matches, cut)
        self.findings.extend(
            GuardrailFinding(rule=m.rule, category="pii")
            for m in matches
            if m.end <= cut
        )
        self._buffer = self._buffer[cut:]
        return emitted

    def _refuse(self, first: PiiMatch) -> str:
        self.refused = True
        self.findings.append(GuardrailFinding(rule=first.rule, category="pii"))
        clean_prefix = self._buffer[: first.start]
        self._buffer = ""
        return clean_prefix + REFUSAL_TEXT

    def _cut_point(self, matches: list[PiiMatch]) -> int:
        """How much of the buffer can be released now."""
        buffer = self._buffer
        trailing_word = len(buffer) - _last_whitespace(buffer, len(buffer)) - 1
        hold = max(MAX_SPACED_PII, min(trailing_word, MAX_EMAIL))
        cut = len(buffer) - hold
        if cut <= 0:
            return 0
        # Start the kept buffer at a word start, so lookbehinds (`\b`, "not
        # preceded by a digit") see the same context as in the full text.
        boundary = _last_whitespace(buffer, cut)
        if boundary >= 0:
            cut = boundary + 1
        # Never release half of a match.
        for match in matches:
            if match.start < cut < match.end:
                cut = match.start
        return cut


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

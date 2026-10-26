"""Streaming PII redaction that never splits a match across chunks."""

import re
from typing import Literal

from sensai.domain.models import GuardrailFinding
from sensai.eval.guardrails.pii import find_pii, substitute
from sensai.eval.guardrails.pii_rules import PII_RULES
from sensai.eval.guardrails.pii_types import PiiMatch, PiiRule

REFUSAL_TEXT = "[response withheld: it contained personal data]"

# Tail kept back while streaming, since later text can complete a match:
# spaced formats (IBAN) fit in 48 chars, an email (no spaces) in 320.
MAX_SPACED_PII = 48
MAX_EMAIL = 320
_WHITESPACE = " \t\r\n"
# A number written in groups ("18 446 744 073 709 551 616") is released whole:
# its tail alone can pass for a card. Longer runs than this are cut anyway, so a
# hostile stream of digits cannot make the buffer grow without bound.
MAX_NUMBER_RUN = 2 * MAX_SPACED_PII
_NUMBER_TAIL = re.compile(r"\d[\d \t-]*\Z")
_NUMBER_HEAD = re.compile(r"[\d \t-]*\d")
_EMAIL_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%+-@"
)


def _last_whitespace(text: str, before: int) -> int:
    """Index of the last whitespace char strictly before `before`, or -1."""
    return max(text.rfind(ch, 0, before) for ch in _WHITESPACE)


def _trailing_email_run(text: str) -> int:
    """Length of the email-character run at the end of `text`, capped at MAX_EMAIL."""
    length = 0
    for char in reversed(text):
        if char not in _EMAIL_CHARS or length >= MAX_EMAIL:
            break
        length += 1
    return length


def _before_number(buffer: str, cut: int) -> int:
    """Move `cut` back before a number it would split, to that number's word start."""
    if cut <= 0 or not _NUMBER_HEAD.match(buffer, cut):
        return cut  # nothing numeric continues after the cut
    floor = max(0, cut - MAX_NUMBER_RUN)
    run = _NUMBER_TAIL.search(buffer, floor, cut)
    if run is None or (run.start() == floor and floor > 0):
        return cut  # no number before the cut, or one too long to hold back
    # Back to a word start too, so `\b` sees the same context as in the full text.
    return _last_whitespace(buffer, run.start()) + 1


class PiiOutputStream:
    """Redacts (or refuses) PII in a stream of chunks, without splitting matches."""

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
        emitted = substitute(self._buffer, matches, cut)
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
        hold = max(MAX_SPACED_PII, _trailing_email_run(buffer))
        cut = len(buffer) - hold
        if cut <= 0:
            return 0
        # Keep a word start so lookbehinds see the same context as in full text.
        boundary = _last_whitespace(buffer, cut)
        if boundary >= 0:
            cut = boundary + 1
        cut = _before_number(buffer, cut)
        # Never release half of a match.
        for match in matches:
            if match.start < cut < match.end:
                cut = match.start
        return cut

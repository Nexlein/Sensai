"""Streaming PII redaction that never splits a match across chunks."""

from typing import Literal

from sensai.domain.models import GuardrailFinding
from sensai.eval.guardrails.pii import find_pii, substitute
from sensai.eval.guardrails.pii_rules import PII_RULES
from sensai.eval.guardrails.pii_types import PiiMatch, PiiRule

REFUSAL_TEXT = "[response withheld: it contained personal data]"

# Streaming hold-back. A match can only be completed by text still to come, so
# the tail of the buffer is kept until it can no longer be part of a match.
# - spaced formats (IBAN <= 34 chars + 8 spaces) never exceed 48 chars;
# - an email has no spaces, so a partial one lives inside the trailing run of
#   characters an email can contain, and is at most 64 + 1 + 253 chars.
MAX_SPACED_PII = 48
MAX_EMAIL = 320
_WHITESPACE = " \t\r\n"
_EMAIL_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%+-@"
)


def _last_whitespace(text: str, before: int) -> int:
    """Index of the last whitespace char strictly before `before`, or -1."""
    return max(text.rfind(ch, 0, before) for ch in _WHITESPACE)


def _trailing_email_run(text: str) -> int:
    """Length of the run of email characters at the end of `text`, capped.

    Measured on email characters, not on "the last word": text written without
    spaces (Chinese, Japanese) has no word breaks, and holding the whole tail back
    would delay it by MAX_EMAIL characters for nothing. Scanning from the end and
    stopping at the cap keeps the cost independent of the buffer size.
    """
    length = 0
    for char in reversed(text):
        if char not in _EMAIL_CHARS or length >= MAX_EMAIL:
            break
        length += 1
    return length


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

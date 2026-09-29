"""PII detection and redaction over plain text."""

from sensai.eval.guardrails.pii_rules import PII_RULES
from sensai.eval.guardrails.pii_types import PiiMatch, PiiRule


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


def substitute(text: str, matches: list[PiiMatch], upto: int) -> str:
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
    return substitute(text, matches, len(text)), matches

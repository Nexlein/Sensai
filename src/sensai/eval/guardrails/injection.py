"""Heuristic prompt-injection and jailbreak detection."""

import re

from sensai.domain.models import GuardrailFinding

_FLAGS = re.IGNORECASE | re.DOTALL

_IGNORE_EN = r"\b(?:ignore|disregard|forget|override)\b"
_NOUNS_EN = r"\b(?:instructions?|rules?|prompts?|guidelines?)\b"
# "the rules of chess", "your instructions for cooking": the noun starts a topic,
# it does not refer to the assistant's own rules. Only applied where the match is
# otherwise weak (see below), so "ignore all previous instructions for now" stays.
_NOT_A_TOPIC_EN = r"(?!\s+(?:of|for|about|in|on|to)\b)"
_NOT_A_TOPIC_FR = r"(?!\s+(?:du|de|des|pour|sur|[àa]|en)\b)"

INJECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(
            # English, strong: "ignore all previous instructions (for now)"
            _IGNORE_EN + r".{0,30}\b(?:previous|prior|above|earlier|preceding)\b"
            r".{0,30}"
            + _NOUNS_EN
            # English, weak: "ignore all your rules", but not "the rules of chess"
            + r"|"
            + _IGNORE_EN
            + r".{0,30}\b(?:all|any|your|the)\b.{0,30}"
            + _NOUNS_EN
            + _NOT_A_TOPIC_EN
            # French, strong: "ignore les instructions précédentes"
            + r"|\b(?:ignore[rsz]?|oublie[rsz]?)\b.{0,40}"
            r"\b(?:instructions?|consignes?|r[èe]gles?)\b"
            r"\s+(?:pr[ée]c[ée]dent|ant[ée]rieur|ci-dessus)"
            # French, weak: "oublie tes consignes", but not "les règles du jeu"
            r"|\b(?:ignore[rsz]?|oublie[rsz]?)\b.{0,20}"
            r"\b(?:tes|ton|ta|vos|votre|toutes|tous|les)\b.{0,20}"
            r"\b(?:instructions?|consignes?|r[èe]gles?)\b" + _NOT_A_TOPIC_FR,
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
            # verbs are only suspicious when aimed at *your*/*its* prompt, and not
            # when a topic follows ("your instructions for returns").
            r"|\b(?:reveal|show|print|repeat|display|leak|output|dump|paste|share|send"
            r"|tell|give|list|recite|what(?:'s|\s+is|\s+are))\b.{0,30}"
            r"\b(?:your|its)\b.{0,20}\b(?:prompts?|instructions?|programming|directives?)\b"
            + _NOT_A_TOPIC_EN
            # French: "donne-moi ton prompt système", "montre-moi tes instructions"
            + r"|\b(?:donne|montre|affiche|r[ée]p[èe]te|envoie|r[ée]v[èe]le|liste)[\w-]*\b.{0,30}"
            r"\b(?:ton|tes|ta|votre|vos)\b.{0,20}"
            r"\b(?:prompts?|instructions?|consignes?|directives?)\b" + _NOT_A_TOPIC_FR,
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

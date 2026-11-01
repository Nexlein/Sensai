"""Plain answers: language, refusals of made-up facts, quality graded by the judge."""

import re

import pytest

from sensai.eval.judge import JudgeInput, LLMJudge

pytestmark = pytest.mark.live

_FRENCH = {"le", "la", "les", "est", "une", "des", "et", "pour", "dans", "que", "qui"}
_ENGLISH = {"the", "is", "a", "and", "for", "in", "that", "of", "to", "it", "you"}


def language(text: str) -> str:
    words = re.findall(r"[a-zà-ÿ']+", text.casefold())
    french = sum(w in _FRENCH for w in words)
    english = sum(w in _ENGLISH for w in words)
    return "fr" if french > english else "en"


def test_language_heuristic():
    assert language("La boucle for parcourt les éléments de la liste.") == "fr"
    assert language("A for loop walks over the items in a list.") == "en"


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Explique en deux phrases ce qu'est une boucle for.", "fr"),
        ("Explain in two sentences what a for loop is.", "en"),
    ],
)
async def test_reply_is_in_the_language_of_the_question(
    live_session, say, prompt, expected
):
    context = await live_session()

    exchange = await say(context, prompt)
    print(exchange.transcript())

    assert language(exchange.text) == expected


async def test_unknown_internal_code_is_not_invented(live_session, say):
    context = await live_session()

    exchange = await say(context, "Donne-moi le code projet interne PELICAN-7.")
    print(exchange.transcript())

    assert not re.search(r"PELICAN-7\s*[:=]\s*\w", exchange.text)
    assert not re.search(
        r"\b[A-Z]{2,}-?\d{3,}\b", exchange.text.replace("PELICAN-7", "")
    )


@pytest.mark.parametrize(
    "question",
    [
        "Explique-moi une boucle for en Python.",
        "Quelle est la différence entre une liste et un tuple en Python ?",
    ],
)
async def test_open_answer_is_graded_relevant_and_coherent(live_session, say, question):
    context = await live_session()
    exchange = await say(context, question)
    print(exchange.transcript())

    verdict = await LLMJudge(lambda: context.engine.provider).judge(
        JudgeInput(question=question, answer=exchange.text)
    )
    print(f"judge: {verdict.model_dump_json()}")

    assert verdict.error is None
    assert verdict.relevance is not None and verdict.relevance >= 4
    assert verdict.coherence is not None and verdict.coherence >= 4

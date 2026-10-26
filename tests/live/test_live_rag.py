"""RAG on the shipped corpus (data/collecte): answers must follow the documents.

Needs the embedding model of `[rag] model` (nomic-embed-text) pulled in Ollama.
"""

from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parents[2] / "data" / "collecte"

pytestmark = pytest.mark.live


@pytest.fixture
async def rag_session(live_session):
    return await live_session(f'[rag]\nenabled = true\ndir = "{CORPUS}"\n')


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Quel jour passe le bac jaune dans le secteur B ?", "mercredi"),
        ("À quelle heure commence la collecte dans le secteur D ?", "13"),
        ("Quelle est la vitesse maximale avec un ripeur sur le marchepied ?", "25"),
    ],
)
async def test_answer_comes_from_the_corpus(rag_session, say, question, expected):
    exchange = await say(rag_session, question)
    print(exchange.transcript())

    assert expected in exchange.text.casefold()


async def test_false_premise_is_corrected_by_the_corpus(rag_session, say):
    exchange = await say(
        rag_session, "Rappelle-moi la règle des 40 km/h sur le marchepied."
    )
    print(exchange.transcript())

    assert "25" in exchange.text


async def test_leading_question_is_not_confirmed(rag_session, say):
    exchange = await say(rag_session, "Le bac jaune du secteur B passe bien le lundi ?")
    print(exchange.transcript())

    assert "mercredi" in exchange.text.casefold()

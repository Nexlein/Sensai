"""RAG end to end: index at startup, retrieve per turn, cite in the prompt."""

import pytest


class KeywordEmbeddings:
    """Stands in for the Ollama embedder: one axis per topic keyword."""

    TOPICS = ("jaune", "neige")

    def __init__(self, base_url: str, model: str) -> None:
        pass

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [
            [1.0 if topic in text.lower() else 0.01 for topic in self.TOPICS]
            for text in texts
        ]


@pytest.fixture
def corpus(workspace, monkeypatch):
    monkeypatch.setattr(
        "sensai.core.bootstrap.OllamaEmbeddingProvider", KeywordEmbeddings
    )
    docs = workspace / "docs"
    docs.mkdir()
    (docs / "calendrier.md").write_text(
        "Le bac jaune du secteur B est collecté le mercredi.", encoding="utf-8"
    )
    (docs / "hiver.md").write_text(
        "En cas de neige, le plan Hérisson suspend les tournées.", encoding="utf-8"
    )
    return docs


def rag_message(call) -> str | None:
    marker = "retrieved documents"
    found = [
        m.content for m in call.messages if m.role == "system" and marker in m.content
    ]
    return found[0] if found else None


async def test_the_closest_document_reaches_the_prompt_with_its_source(
    corpus, open_session, say
):
    context = await open_session(
        "Le mercredi.", config='[rag]\nenabled = true\ndir = "docs"\ntop_k = 1\n'
    )

    exchange = await say(context, "Quel jour passe le bac jaune dans le secteur B ?")

    rag = rag_message(context.engine.provider.calls[0])
    assert rag is not None
    assert "mercredi" in rag
    assert "calendrier.md" in rag
    assert "neige" not in rag
    assert exchange.text == "Le mercredi."


async def test_each_turn_retrieves_for_its_own_question(corpus, open_session, say):
    context = await open_session(
        "Le mercredi.",
        "Les tournées sont suspendues.",
        config='[rag]\nenabled = true\ndir = "docs"\ntop_k = 1\n',
    )

    await say(context, "Quand passe le bac jaune ?")
    await say(context, "Que se passe-t-il en cas de neige ?")

    rag = rag_message(context.engine.provider.calls[1])
    assert rag is not None
    assert "hiver.md" in rag


async def test_without_rag_no_document_is_injected(corpus, open_session, say):
    context = await open_session("Je ne sais pas.")

    await say(context, "Quel jour passe le bac jaune ?")

    assert rag_message(context.engine.provider.calls[0]) is None

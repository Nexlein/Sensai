"""RAG A/B benchmark: questions, scoring, conditions."""

from pathlib import Path
from typing import ClassVar

import pytest

from sensai.core.engine import ChatEngine
from sensai.domain.errors import ProviderError
from sensai.domain.models import Conversation, ModelOptions
from sensai.eval.bench import rag
from sensai.eval.bench.rag import (
    Condition,
    Question,
    is_correct,
    is_refusal,
    load_questions,
)

ROOT = Path(__file__).resolve().parents[3]


def test_shipped_questions_load_and_cover_unanswerable_ones():
    questions = load_questions(ROOT / "data" / "bench" / "rag-questions.jsonl")

    assert len(questions) >= 20
    assert sum(q.unanswerable for q in questions) >= 4
    assert all(q.expected for q in questions if not q.unanswerable)


@pytest.mark.parametrize(
    "answer",
    [
        "Je ne trouve pas cette information dans les documents.",
        "Le document ne précise pas.",
    ],
)
def test_refusals_are_recognized(answer):
    assert is_refusal(answer)


def test_correct_needs_every_keyword_group_ignoring_case_and_accents():
    question = Question(1, "q", [["5 h 30", "5h30"], ["secteur a"]])

    assert is_correct(question, "Le SECTEUR A commence à 5h30.")
    assert not is_correct(question, "Le secteur B commence à 5h30.")


def test_unanswerable_questions_need_a_refusal():
    question = Question(2, "salaire ?", [], unanswerable=True)

    assert is_correct(question, "Je ne trouve pas cette information.")
    assert not is_correct(question, "Un ripeur gagne 1 900 euros.")


class FakeRetriever:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def retrieve_context(self, query: str, top_k: int = 5) -> str:
        self.queries.append(query)
        return "--- Source: calendrier-secteurs.md ---\nBac jaune secteur B : mercredi."


class ScriptedProvider:
    """Answers from what the prompt contains, like a model reading its context."""

    def __init__(self, *args, **kwargs) -> None:
        self.prompts: list[list] = []

    async def chat_stream(self, messages, tools=None, think=None):
        from sensai.domain.events import TextChunkEvent, UsageEvent

        self.prompts.append(messages)
        text = " ".join(m.content for m in messages)
        if "mercredi" in text:
            yield TextChunkEvent(content="Le mercredi [calendrier-secteurs.md].")
        else:
            yield TextChunkEvent(content="Je ne trouve pas cette information.")
        yield UsageEvent(prompt_tokens=120, prompt_seconds=0.5, load_seconds=0.1)


async def test_conditions_differ_only_by_retrieval_and_persona(monkeypatch, tmp_path):
    monkeypatch.setattr(rag, "OllamaLLMProvider", ScriptedProvider)
    persona = tmp_path / "persona.md"
    persona.write_text("Tu es Sensai Collecte.")
    questions = [
        Question(1, "Quel jour passe le bac jaune en secteur B ?", [["mercredi"]]),
        Question(2, "Code du portail ?", [], unanswerable=True),
    ]
    retriever = FakeRetriever()

    without = await rag.run_condition(
        Condition("no RAG", rag=False, persona=True),
        questions,
        "m",
        retriever,
        persona,
        "http://x",
    )
    with_rag = await rag.run_condition(
        Condition("RAG", rag=True, persona=False),
        questions,
        "m",
        retriever,
        persona,
        "http://x",
    )

    assert (without.answered_right, without.refused_right) == (0, 1)
    assert (with_rag.answered_right, with_rag.cited) == (1, 1)
    assert with_rag.accuracy == 0.5 + 0.5 * (with_rag.refused_right == 1)
    assert with_rag.median_prompt_tokens == 120
    assert len(retriever.queries) == 2


class FlakyProvider(ScriptedProvider):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    async def chat_stream(self, messages, tools=None, think=None):
        if self.failures:
            self.failures -= 1
            raise ProviderError("provider request failed")
        async for event in super().chat_stream(messages, tools, think):
            yield event


def _engine(provider):
    return ChatEngine(provider, Conversation(), think=False)


async def test_a_dropped_call_is_retried_once(monkeypatch):
    monkeypatch.setattr(rag, "RETRY_WAIT", 0)
    provider = FlakyProvider(failures=1)

    answer, usage = await rag._answer(_engine(provider), "Code du portail ?")

    assert answer == "Je ne trouve pas cette information."
    assert usage is not None
    assert usage.prompt_tokens == 120


async def test_a_second_failure_stops_the_suite(monkeypatch):
    monkeypatch.setattr(rag, "RETRY_WAIT", 0)

    with pytest.raises(ProviderError):
        await rag._answer(_engine(FlakyProvider(failures=2)), "Code du portail ?")


class SamplingProvider(ScriptedProvider):
    """Records the options it was built with; answers right on every other call."""

    instances: ClassVar[list["SamplingProvider"]] = []
    calls: ClassVar[int] = 0

    def __init__(self, *args, options: ModelOptions, **kwargs) -> None:
        super().__init__()
        self.options = options
        SamplingProvider.instances.append(self)

    async def chat_stream(self, messages, tools=None, think=None):
        from sensai.domain.events import TextChunkEvent

        SamplingProvider.calls += 1
        if self.options.temperature and SamplingProvider.calls % 2 == 0:
            yield TextChunkEvent(content="Le jeudi.")
            return
        async for event in super().chat_stream(messages, tools, think):
            yield event


async def test_temperature_runs_each_value_unseeded_and_grades_stability(
    monkeypatch, tmp_path
):
    SamplingProvider.instances = []
    SamplingProvider.calls = 0
    monkeypatch.setattr(rag, "OllamaLLMProvider", SamplingProvider)

    async def fake_retriever(*args, **kwargs):
        return FakeRetriever(), None

    monkeypatch.setattr(rag, "build_retriever", fake_retriever)
    persona = tmp_path / "persona.md"
    persona.write_text("Tu es Sensai Collecte.")
    questions = [
        Question(1, "Quel jour passe le bac jaune en secteur B ?", [["mercredi"]]),
    ]

    results = await rag.bench_temperature(
        "m",
        questions,
        tmp_path,
        persona,
        tmp_path / "db",
        "http://x",
        temperatures=(0.0, 1.0),
        runs=2,
    )

    assert [r.temperature for r in results] == [0.0, 1.0]
    assert all(p.options.seed is None for p in SamplingProvider.instances)
    cold, hot = results
    assert (cold.mean_accuracy, cold.stable, cold.identical) == (1.0, 1, 1)
    assert hot.stable == 0 and hot.identical == 0


class RecordingEmbedder:
    """Stands in for OllamaEmbeddingProvider and records the model it was given."""

    models: ClassVar[list[str]] = []

    def __init__(self, base_url: str, model: str) -> None:
        RecordingEmbedder.models.append(model)

    async def embed_texts(self, texts):
        return [[1.0, float(len(text))] for text in texts]


async def test_retriever_uses_the_embedding_model_and_top_k_it_is_given(
    monkeypatch, tmp_path
):
    RecordingEmbedder.models = []
    monkeypatch.setattr(rag, "OllamaEmbeddingProvider", RecordingEmbedder)
    corpus = tmp_path / "docs"
    corpus.mkdir()
    for name in "abcd":
        (corpus / f"{name}.md").write_text(f"document {name} " * 20)

    retriever, index = await rag.build_retriever(
        corpus, tmp_path / "db", "http://x", embed_model="bge-m3", top_k=2
    )

    assert RecordingEmbedder.models == ["bge-m3"]
    assert retriever.top_k == 2
    assert index.chunks >= 4


def test_bench_cli_defaults_keep_the_published_setup():
    from sensai.eval.bench.__main__ import build_parser

    args = build_parser().parse_args(["rag"])

    assert (args.embed_model, args.top_k) == ("nomic-embed-text", 5)

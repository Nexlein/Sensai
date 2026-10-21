"""RAG A/B: the same questions with and without retrieval, through Sensai's engine.

Questions come from a JSONL file (`data/bench/rag-questions.jsonl`): each one
lists the keywords a right answer contains, or is marked `unanswerable` when the
right answer is to say the documents do not tell. Every condition runs the real
pipeline (`ChatEngine`, guardrails, persona, retriever), not raw Ollama calls.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sensai.core.budget import BudgetConfig, ContextBudget
from sensai.core.components import build_guardrail, load_persona
from sensai.core.config import GuardrailsConfig, PersonaConfig
from sensai.core.engine import ChatEngine
from sensai.domain.events import TextChunkEvent, UsageEvent
from sensai.domain.models import Conversation, ModelOptions
from sensai.eval.bench.models import normalize
from sensai.memory.rag.chunker import TextChunker
from sensai.memory.rag.retriever import RAGRetriever
from sensai.memory.rag.store import SQLiteVectorStore
from sensai.providers.ollama import OllamaEmbeddingProvider, OllamaLLMProvider

REFUSALS = (
    "je ne trouve pas",
    "ne trouve pas",
    "pas cette information",
    "aucune information",
    "pas d'information",
    "ne dispose pas",
    "ne sais pas",
    "pas mentionne",
    "pas precise",
    "ne precise pas",
    "ne contiennent pas",
    "ne contient pas",
    "pas disponible",
    "n'est pas indique",
    "ne mentionne",
    "pas d'acces",
    "ne peux pas",
)


@dataclass(frozen=True)
class Question:
    id: int
    question: str
    expected: list[list[str]]
    unanswerable: bool = False
    source: str | None = None


def load_questions(path: Path) -> list[Question]:
    questions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            data = json.loads(line)
            questions.append(
                Question(
                    id=data["id"],
                    question=data["question"],
                    expected=data.get("expected", []),
                    unanswerable=data.get("unanswerable", False),
                    source=data.get("source"),
                )
            )
    return questions


def is_refusal(answer: str) -> bool:
    plain = normalize(answer)
    return any(pattern in plain for pattern in REFUSALS)


def is_correct(question: Question, answer: str) -> bool:
    """Every keyword group has one alternative in the answer, or a refusal when
    the question has no answer in the documents."""
    if question.unanswerable:
        return is_refusal(answer)
    plain = normalize(answer)
    return all(
        any(normalize(option) in plain for option in group)
        for group in question.expected
    )


@dataclass(frozen=True)
class Condition:
    name: str
    rag: bool
    persona: bool


CONDITIONS = (
    Condition("no RAG, persona", rag=False, persona=True),
    Condition("RAG, generic prompt", rag=True, persona=False),
    Condition("RAG, persona", rag=True, persona=True),
)


@dataclass
class ConditionResult:
    condition: str
    model: str
    correct: int
    answerable: int
    answered_right: int
    unanswerable: int
    refused_right: int
    cited: int
    median_seconds: float
    median_first_token: float
    median_prompt_tokens: int
    answers: list[dict[str, Any]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        total = self.answerable + self.unanswerable
        return self.correct / total if total else 0.0


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0.0


async def run_condition(
    condition: Condition,
    questions: list[Question],
    model: str,
    retriever: RAGRetriever | None,
    persona_file: Path,
    base_url: str,
) -> ConditionResult:
    provider = OllamaLLMProvider(
        base_url=base_url,
        model=model,
        options=ModelOptions(temperature=0, seed=42, num_ctx=8192),
    )
    persona = (
        load_persona(PersonaConfig(name="Sensai Collecte", file=str(persona_file)))
        if condition.persona
        else None
    )
    rows = []
    for question in questions:
        engine = ChatEngine(
            provider,
            Conversation(),
            retriever=retriever if condition.rag else None,
            budget=ContextBudget(BudgetConfig(), None),
            guardrail=build_guardrail(GuardrailsConfig()),
            reasoning=True,
            think=False,
            persona=persona,
        )
        chunks, usage = [], None
        start = time.perf_counter()
        async for event in engine.send(question.question):
            if isinstance(event, TextChunkEvent):
                chunks.append(event.content)
            elif isinstance(event, UsageEvent):
                usage = event
        answer = "".join(chunks)
        rows.append(
            {
                "id": question.id,
                "question": question.question,
                "answer": answer,
                "correct": is_correct(question, answer),
                "refused": is_refusal(answer),
                "unanswerable": question.unanswerable,
                "cited": ".md" in answer,
                "seconds": round(time.perf_counter() - start, 2),
                "first_token": round(usage.first_token_seconds or 0, 2) if usage else 0,
                "prompt_tokens": usage.prompt_tokens if usage else 0,
            }
        )
    answerable = [r for r in rows if not r["unanswerable"]]
    unanswerable = [r for r in rows if r["unanswerable"]]
    return ConditionResult(
        condition=condition.name,
        model=model,
        correct=sum(r["correct"] for r in rows),
        answerable=len(answerable),
        answered_right=sum(r["correct"] for r in answerable),
        unanswerable=len(unanswerable),
        refused_right=sum(r["correct"] for r in unanswerable),
        cited=sum(r["cited"] for r in answerable),
        median_seconds=_median([r["seconds"] for r in rows]),
        median_first_token=_median([r["first_token"] for r in rows]),
        median_prompt_tokens=int(_median([r["prompt_tokens"] or 0 for r in rows])),
        answers=rows,
    )


@dataclass
class IndexResult:
    chunks: int
    seconds: float
    retrieval_seconds: float


async def build_retriever(
    corpus: Path, db: Path, base_url: str, embed_model: str = "nomic-embed-text"
) -> tuple[RAGRetriever, IndexResult]:
    """Index the corpus once and time indexing and one retrieval."""
    retriever = RAGRetriever(
        OllamaEmbeddingProvider(base_url=base_url, model=embed_model),
        SQLiteVectorStore(str(db)),
    )
    start = time.perf_counter()
    count = await retriever.index_directory(str(corpus), TextChunker())
    indexed = time.perf_counter() - start
    start = time.perf_counter()
    await retriever.retrieve_context("Quel jour passe le bac jaune ?")
    return retriever, IndexResult(count, indexed, time.perf_counter() - start)


async def bench_rag(
    model: str,
    questions: list[Question],
    corpus: Path,
    persona_file: Path,
    db: Path,
    base_url: str,
    conditions: tuple[Condition, ...] = CONDITIONS,
) -> tuple[IndexResult, list[ConditionResult]]:
    retriever, index = await build_retriever(corpus, db, base_url)
    results = [
        await run_condition(
            condition, questions, model, retriever, persona_file, base_url
        )
        for condition in conditions
    ]
    return index, results

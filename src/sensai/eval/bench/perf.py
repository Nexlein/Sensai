"""How long Sensai's own code takes, without any model.

Each case times one operation on realistic input sizes. The model call is
replaced by a mock that answers at once, so what remains is pure overhead:
what Sensai adds on top of the model, per turn, per chunk or at start-up.
"""

import os
import random
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sensai.core.bootstrap import build_session
from sensai.core.budget import BudgetConfig, ContextBudget
from sensai.core.config import AppConfig, load_config, save_config
from sensai.core.engine import ChatEngine
from sensai.core.prompt import PromptComposer
from sensai.core.settings import format_settings, sources
from sensai.core.turn import Turn
from sensai.domain.models import Chunk, Conversation, Document
from sensai.eval.bench.timing import Stat, human_seconds, measure, measure_async, table
from sensai.eval.guardrails import RegexGuardrail, find_injection, redact_pii
from sensai.eval.guardrails.stream import PiiOutputStream
from sensai.interfaces.diff import parse_diff
from sensai.memory.manager import SqliteMemoryManager
from sensai.memory.rag.chunker import TextChunker
from sensai.memory.rag.store import SQLiteVectorStore, cosine_similarity
from sensai.memory.session import SqliteMemoryStore
from sensai.providers.mock import MockLLMProvider
from sensai.tools.fs import WriteFileTool
from sensai.tools.registry import build_default_registry

FRENCH = (
    "Le bac jaune du secteur B est collecté le mercredi à partir de 6 h. "
    "Les ripeurs ne montent sur le marchepied que véhicule à l'arrêt. "
)
EMBEDDING_SIZE = 768


@dataclass(frozen=True)
class PerfResult:
    """One measured case: what was timed, on what size, how long."""

    group: str
    name: str
    size: str
    stat: Stat

    def row(self) -> list[str]:
        return [
            self.group,
            self.name,
            self.size,
            human_seconds(self.stat.median),
            human_seconds(self.stat.best),
        ]


@contextmanager
def _in_temp_dir() -> Iterator[Path]:
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="sensai-bench-") as folder:
        os.chdir(folder)
        try:
            yield Path(folder)
        finally:
            os.chdir(previous)


def _conversation(turns: int) -> Conversation:
    conversation = Conversation()
    for index in range(turns):
        conversation.add_message("user", f"Question {index}: {FRENCH}")
        conversation.add_message("assistant", f"Réponse {index}: {FRENCH * 2}")
    return conversation


def _vectors(count: int, seed: int = 7) -> list[list[float]]:
    rng = random.Random(seed)
    return [[rng.uniform(-1, 1) for _ in range(EMBEDDING_SIZE)] for _ in range(count)]


def _startup(repeat: int) -> Stat:
    """Fresh interpreter importing the CLI entry point, as `sensai` does."""
    runs = []
    for _ in range(repeat):
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", "import sensai.interfaces.dispatcher"], check=True
        )
        runs.append(time.perf_counter() - start)
    return Stat(tuple(runs))


def _engine_turn(guarded: bool, reply_words: int) -> Callable[[], object]:
    reply = " ".join(["mot"] * reply_words)
    engine = ChatEngine(
        MockLLMProvider(default_response=reply, simulated_delay=0),
        Conversation(),
        guardrail=RegexGuardrail() if guarded else None,
        budget=ContextBudget(BudgetConfig(), None),
    )

    async def turn() -> None:
        engine.conversation = Conversation()
        async for _ in engine.send("Quel jour passe le bac jaune ?"):
            pass

    return turn


def _stream_filter(chunks: list[str]) -> Callable[[], object]:
    def run() -> None:
        stream = PiiOutputStream()
        for chunk in chunks:
            stream.feed(chunk)
        stream.flush()

    return run


def run_perf(repeat: int = 5, quick: bool = False) -> list[PerfResult]:
    """Every case, smallest sizes only when `quick`."""
    results: list[PerfResult] = []

    def add(group: str, name: str, size: str, stat: Stat) -> None:
        results.append(PerfResult(group, name, size, stat))

    add("startup", "import CLI entry point (new process)", "-", _startup(repeat))

    short, long = FRENCH, FRENCH * 80
    guardrail = RegexGuardrail()
    for label, text in (("130 chars", short), ("10 kB", long)):
        add(
            "guardrails",
            "input filter (injection + PII)",
            label,
            measure_async(lambda text=text: guardrail.filter_input(text), repeat, 20),
        )
        add(
            "guardrails",
            "injection rules only",
            label,
            measure(lambda text=text: find_injection(text), repeat, 20),
        )
        add(
            "guardrails",
            "PII masking only",
            label,
            measure(lambda text=text: redact_pii(text), repeat, 20),
        )
    reply = FRENCH * 8
    chunks = [reply[i : i + 4] for i in range(0, len(reply), 4)]
    add(
        "guardrails",
        "streamed reply filter, 4-char chunks",
        f"{len(chunks)} chunks",
        measure(_stream_filter(chunks), repeat),
    )
    add(
        "guardrails",
        "streamed reply filter, per chunk",
        "1 chunk",
        Stat(
            tuple(r / len(chunks) for r in measure(_stream_filter(chunks), repeat).runs)
        ),
    )

    for words in (50, 500):
        for guarded in (False, True):
            add(
                "engine",
                f"full turn, mock model, guardrails {'on' if guarded else 'off'}",
                f"{words} words",
                measure_async(_engine_turn(guarded, words), repeat),
            )

    sizes = (10, 100) if quick else (10, 100, 1000)
    for turns in sizes:
        conversation = _conversation(turns)
        composer = PromptComposer(
            conversation, ContextBudget(BudgetConfig(max_tokens=10**9), None)
        )
        add(
            "prompt",
            "compose prompt (fit budget + system notes)",
            f"{turns * 2} msgs",
            measure_async(lambda c=composer: c.compose_parts(Turn("q"), True), repeat),
        )

    registry = build_default_registry(".", web_search=True, sandbox=True)
    add(
        "tools",
        "tool schema for the model",
        "10 tools",
        measure(registry.get_tools_schema, repeat, 100),
    )
    with _in_temp_dir() as folder:
        old = "\n".join(f"ligne {i}" for i in range(1000))
        new = old.replace("ligne 5", "ligne cinq")
        (folder / "big.md").write_text(old)
        writer = WriteFileTool(folder)
        add(
            "tools",
            "write_file preview diff",
            "1000 lines",
            measure(lambda: writer.preview("big.md", new), repeat),
        )
        diff = writer.preview("big.md", new) or ""
        add(
            "tools",
            "parse diff for the confirmation",
            "1000 lines",
            measure(lambda: parse_diff(diff), repeat),
        )

        store = SqliteMemoryStore(folder / "s.db")
        for turns in sizes:
            conversation = _conversation(turns)
            add(
                "memory",
                "save session (every turn)",
                f"{turns * 2} msgs",
                measure_async(lambda c=conversation: store.save(c), repeat),
            )
            add(
                "memory",
                "load session (--session)",
                f"{turns * 2} msgs",
                measure_async(lambda c=conversation: store.load(c.id), repeat),
            )

        facts = SqliteMemoryManager(folder / "m.db")
        for index in range(1000 if not quick else 100):
            facts.store_fact(f"entity{index % 50}", f"key{index}", f"value {index}")
        add(
            "memory",
            "store one fact",
            "-",
            measure(lambda: facts.store_fact("user", "secteur", "B"), repeat, 10),
        )
        add(
            "memory",
            "format facts for the prompt",
            "20 facts",
            measure(facts.format_context, repeat, 10),
        )
        add(
            "memory",
            "search facts (LIKE)",
            "1000 facts",
            measure(lambda: facts.search_facts("value 9"), repeat, 10),
        )

        corpus = Path(__file__).resolve().parents[4] / "data" / "collecte"
        text = (
            "\n".join(p.read_text() for p in sorted(corpus.glob("*.md")))
            if corpus.is_dir()
            else FRENCH * 100
        )
        chunker = TextChunker()
        docs = [Document(path="corpus", content=text * 10)]
        add(
            "rag",
            "chunk documents",
            f"{len(text) * 10 // 1000} kB",
            measure(lambda: chunker.chunk_documents(docs), repeat),
        )
        query = _vectors(1, seed=1)[0]
        add(
            "rag",
            "cosine similarity",
            f"{EMBEDDING_SIZE} dims",
            measure(lambda: cosine_similarity(query, query), repeat, 100),
        )
        for count in (100, 1000) if quick else (100, 1000, 5000):
            vectors = SQLiteVectorStore(str(folder / f"v{count}.db"))
            vectors.replace_chunks(
                [
                    Chunk(id=str(i), doc_id="d", text=FRENCH, embedding=vector)
                    for i, vector in enumerate(_vectors(count))
                ]
            )
            add(
                "rag",
                "vector search (load all + cosine)",
                f"{count} chunks",
                measure(lambda v=vectors: v.search(query, 5), max(3, repeat // 2)),
            )

        config_path = folder / "sensai.toml"
        config = AppConfig(model="llama3.2")
        save_config(config, config_path)
        add(
            "config",
            "load sensai.toml",
            "-",
            measure(lambda: load_config(config_path), repeat, 10),
        )
        add(
            "config",
            "save sensai.toml (keeps comments)",
            "-",
            measure(lambda: save_config(config, config_path), repeat, 10),
        )
        add(
            "config",
            "/config show",
            "41 keys",
            measure(
                lambda: format_settings(config, sources(config, config_path)),
                repeat,
                10,
            ),
        )

        async def session() -> None:
            context = await build_session(config_path=config_path, provider_name="mock")
            await context.aclose()

        add(
            "startup",
            "build session (mock model, no RAG/MCP)",
            "-",
            measure_async(session, repeat),
        )

    return results


def perf_table(results: list[PerfResult]) -> str:
    return table(
        ["area", "operation", "size", "median", "best"], [r.row() for r in results]
    )

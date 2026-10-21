"""Model benchmarks through Ollama: speed, memory, tool choice and thinking effort.

Every call fixes `temperature = 0` and `seed = 42` so a rerun on the same machine
finds the same orders of magnitude.
"""

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from sensai.core.prompt import TOOL_USE_GUIDANCE
from sensai.eval.bench.ollama import ChatResult, OllamaBench
from sensai.tools.registry import build_default_registry

FIXED = {"temperature": 0, "seed": 42}
SPEED_TEXT = (
    "La Régie de collecte du Val-Brûlé collecte les ordures ménagères, les emballages, "
    "les biodéchets et les encombrants de 38 communes. Les bacs sont sortis la veille "
    "après 19 h. Le bac jaune reçoit tous les emballages vidés, le bac marron les "
    "biodéchets dans des sacs kraft, le bac gris le reste. "
)
SPEED_QUESTION = "Résume ce texte en trois phrases courtes."


def normalize(text: str) -> str:
    """Lowercase, accents removed, spaces squeezed: for keyword matching."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain)


def think_off(client: OllamaBench, model: str) -> bool | None:
    """`False` for a model that thinks by default, None for one that cannot think."""
    return False if "thinking" in client.capabilities(model) else None


@dataclass
class SpeedResult:
    model: str
    parameters: str
    quantization: str
    load_seconds: float
    prompt_tokens: int
    prompt_rate: float
    reply_rate: float
    first_token_seconds: float
    reply_seconds: float
    memory_bytes: int
    vram_bytes: int
    context_length: int | None
    error: str = ""


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0.0


def bench_speed(
    client: OllamaBench, model: str, runs: int = 3, reply_tokens: int = 128
) -> SpeedResult:
    """Cold load, then `runs` warm calls on a ~400-token prompt.

    Each warm call starts with a different line so Ollama cannot reuse the
    cached prefix: the prefill rate stays a real prefill rate.
    """
    think = think_off(client, model)
    options = {**FIXED, "num_predict": reply_tokens}
    client.unload_all()

    def call(salt: int) -> ChatResult:
        text = f"Note {salt}.\n" + SPEED_TEXT * 6 + "\n" + SPEED_QUESTION
        return client.chat(model, [{"role": "user", "content": text}], options, think)

    cold = call(0)
    warm = [call(index) for index in range(1, runs + 1)]
    entry = next((m for m in client.loaded() if m.name == model), None)
    details = entry.details if entry else {}
    return SpeedResult(
        model=model,
        parameters=str(details.get("parameter_size", "?")),
        quantization=str(details.get("quantization_level", "?")),
        load_seconds=cold.load_seconds,
        prompt_tokens=_median([r.prompt_tokens for r in warm]),
        prompt_rate=_median([r.prompt_rate or 0 for r in warm]),
        reply_rate=_median([r.reply_rate or 0 for r in warm]),
        first_token_seconds=_median([r.first_token_seconds for r in warm]),
        reply_seconds=_median([r.wall_seconds for r in warm]),
        memory_bytes=entry.size if entry else 0,
        vram_bytes=entry.size_vram if entry else 0,
        context_length=entry.context_length if entry else None,
    )


@dataclass(frozen=True)
class ToolCase:
    """A message and the tool a good assistant calls for it (None: answer directly)."""

    prompt: str
    expected: str | None
    argument: tuple[str, str] | None = None


TOOL_CASES = (
    ToolCase("Bonjour, tu vas bien ?", None),
    ToolCase("Explique en une phrase ce qu'est un ripeur.", None),
    ToolCase("Combien font 12 + 30 ?", None),
    ToolCase("What is the capital of France?", None),
    ToolCase(
        "Lis le fichier data/collecte/consignes-tri.md",
        "read_file",
        ("path", "consignes-tri.md"),
    ),
    ToolCase("Quels fichiers y a-t-il dans le dossier data/collecte ?", "list_dir"),
    ToolCase(
        "Écris « bonjour » dans le fichier notes/test.md",
        "write_file",
        ("path", "notes/test.md"),
    ),
    ToolCase(
        "Cherche sur le web la date de l'obligation de tri des biodéchets en France.",
        "web_search",
    ),
    ToolCase("Retiens que mon secteur de collecte est le B.", "remember_fact"),
    ToolCase(
        "Exécute un script Python qui calcule 4817 * 2309 et affiche le résultat.",
        "run_python",
    ),
)


class _NoMemory:
    """Stands in for the memory store: only the tool schemas are needed here."""


def tool_schemas() -> list[dict[str, Any]]:
    """The tool definitions Sensai sends by default (files, web, memory, sandbox)."""
    registry = build_default_registry(".", memory=_NoMemory())  # type: ignore[arg-type]
    return registry.get_tools_schema()


@dataclass
class ToolResult:
    model: str
    passed: int
    total: int
    false_calls: int
    missed_calls: int
    wrong_tool: int
    median_seconds: float
    cases: list[dict[str, Any]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


def judge_tool_case(case: ToolCase, result: ChatResult) -> str:
    """`ok`, `false_call` (tool for a plain question), `missed`, `wrong_tool`, `bad_args`."""
    names = result.tool_names
    if case.expected is None:
        return "ok" if not names else "false_call"
    if not names:
        return "missed"
    if case.expected not in names:
        return "wrong_tool"
    if case.argument is not None:
        key, needle = case.argument
        call = next(
            c for c in result.tool_calls if c["function"]["name"] == case.expected
        )
        if needle not in str(call["function"].get("arguments", {}).get(key, "")):
            return "bad_args"
    return "ok"


def bench_tools(
    client: OllamaBench, model: str, cases: tuple[ToolCase, ...] = TOOL_CASES
) -> ToolResult:
    """One call per case, with Sensai's tool guidance and tool schemas."""
    think = think_off(client, model)
    tools = tool_schemas()
    if "tools" not in client.capabilities(model):
        return ToolResult(model, 0, len(cases), 0, 0, 0, 0.0, [{"error": "no tools"}])
    verdicts, times, details = [], [], []
    for case in cases:
        messages = [
            {"role": "system", "content": TOOL_USE_GUIDANCE},
            {"role": "user", "content": case.prompt},
        ]
        result = client.chat(
            model, messages, {**FIXED, "num_predict": 256}, think, tools
        )
        verdict = judge_tool_case(case, result)
        verdicts.append(verdict)
        times.append(result.wall_seconds)
        details.append(
            {
                "prompt": case.prompt,
                "expected": case.expected,
                "called": result.tool_names,
                "verdict": verdict,
                "seconds": round(result.wall_seconds, 2),
            }
        )
    return ToolResult(
        model=model,
        passed=verdicts.count("ok"),
        total=len(cases),
        false_calls=verdicts.count("false_call"),
        missed_calls=verdicts.count("missed"),
        wrong_tool=verdicts.count("wrong_tool") + verdicts.count("bad_args"),
        median_seconds=_median(times),
        cases=details,
    )


EFFORT_QUESTION = (
    "Un camion fait 3 tournées de 42 km puis 2 tournées de 37 km. "
    "Quelle distance totale a-t-il parcourue ? Réponds par un nombre."
)
EFFORT_ANSWER = "200"


@dataclass
class EffortResult:
    model: str
    effort: str
    correct: bool
    thinking_chars: int
    reply_tokens: int
    seconds: float


def bench_effort(
    client: OllamaBench,
    model: str,
    levels: tuple[bool | str, ...] = (False, "low", "medium", "high"),
) -> list[EffortResult]:
    """Same arithmetic question at each thinking effort: cost against correctness."""
    results = []
    for level in levels:
        result = client.chat(
            model,
            [{"role": "user", "content": EFFORT_QUESTION}],
            {**FIXED, "num_predict": 4096},
            level,
        )
        results.append(
            EffortResult(
                model=model,
                effort="off" if level is False else str(level),
                correct=EFFORT_ANSWER in result.content.replace(" ", ""),
                thinking_chars=len(result.thinking),
                reply_tokens=result.reply_tokens,
                seconds=result.wall_seconds,
            )
        )
    return results


def as_dicts(items: list[Any]) -> list[dict[str, Any]]:
    return [asdict(item) for item in items]

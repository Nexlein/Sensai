"""Context limits: how the prompt size changes speed, memory and recall.

A "needle" fact is hidden at several depths of a long French filler text and
the model is asked for it. Run with growing `num_ctx` this shows the cost of a
bigger window (prefill time, KV cache memory) and where recall breaks. Run
without `num_ctx` it shows Ollama silently cutting a prompt longer than its
default window.
"""

from dataclasses import dataclass
from pathlib import Path

from sensai.core.budget.tokens import count_text
from sensai.eval.bench.models import FIXED, think_off
from sensai.eval.bench.ollama import OllamaBench

NEEDLE = "Note interne : le code du portail du dépôt est 4471."
QUESTION = "D'après le texte ci-dessus, quel est le code du portail du dépôt ? Réponds par le code seul."
ANSWER = "4471"
CORPUS = Path(__file__).resolve().parents[4] / "data" / "collecte"


def filler_text() -> str:
    """The scenario corpus, used as realistic French filler."""
    if CORPUS.is_dir():
        return "\n\n".join(
            p.read_text(encoding="utf-8") for p in sorted(CORPUS.glob("*.md"))
        )
    return "La collecte des bacs suit le calendrier du secteur. " * 200


def haystack(filler: str, chars: int, depth: float) -> str:
    """`chars` characters of filler with the needle at `depth` (0 = start, 1 = end)."""
    body = (filler * (chars // max(len(filler), 1) + 1))[:chars]
    cut = body.rfind("\n", 0, int(len(body) * depth))
    cut = cut if cut > 0 else int(len(body) * depth)
    return f"{body[:cut]}\n{NEEDLE}\n{body[cut:]}"


@dataclass
class ContextResult:
    model: str
    num_ctx: int | None
    depth: float
    prompt_chars: int
    estimated_tokens: int
    prompt_tokens: int
    found: bool
    prefill_rate: float
    first_token_seconds: float
    memory_bytes: int
    server_context: int | None


def chars_per_token(client: OllamaBench, model: str) -> float:
    """Measured on the filler, to size prompts in real tokens for this model."""
    sample = filler_text()[:6000]
    result = client.chat(
        model,
        [{"role": "user", "content": sample}],
        {**FIXED, "num_predict": 1, "num_ctx": 8192},
        think_off(client, model),
    )
    return len(sample) / max(result.prompt_tokens, 1)


def bench_context(
    client: OllamaBench,
    model: str,
    sizes: tuple[int, ...] = (2048, 4096, 8192, 16384, 32768),
    depths: tuple[float, ...] = (0.1, 0.5, 0.9),
    fill: float = 0.8,
    deep_limit: int = 8192,
) -> list[ContextResult]:
    """For each `num_ctx`, a prompt filling `fill` of it, needle at each depth.

    Above `deep_limit` only the middle depth is run: those prompts take minutes
    on a CPU.
    """
    think = think_off(client, model)
    ratio = chars_per_token(client, model)
    filler = filler_text()
    results = []
    for size in sizes:
        client.unload_all()
        for depth in depths if size <= deep_limit else (0.5,):
            text = haystack(filler, int(size * fill * ratio), depth)
            results.append(
                _ask(
                    client,
                    model,
                    think,
                    text,
                    depth,
                    {**FIXED, "num_ctx": size, "num_predict": 32},
                )
            )
    return results


def bench_truncation(
    client: OllamaBench, model: str, target_tokens: int = 6000
) -> list[ContextResult]:
    """A prompt over Ollama's default window, without and with a big enough `num_ctx`.

    With the needle near the start, a silently cut prompt loses it.
    """
    think = think_off(client, model)
    text = haystack(
        filler_text(), int(target_tokens * chars_per_token(client, model)), 0.05
    )
    client.unload_all()
    default = _ask(client, model, think, text, 0.05, {**FIXED, "num_predict": 32})
    client.unload_all()
    sized = _ask(
        client, model, think, text, 0.05, {**FIXED, "num_predict": 32, "num_ctx": 8192}
    )
    return [default, sized]


def _ask(
    client: OllamaBench,
    model: str,
    think: bool | None,
    text: str,
    depth: float,
    options: dict,
) -> ContextResult:
    result = client.chat(
        model, [{"role": "user", "content": f"{text}\n\n{QUESTION}"}], options, think
    )
    entry = next((m for m in client.loaded() if m.name == model), None)
    return ContextResult(
        model=model,
        num_ctx=options.get("num_ctx"),
        depth=depth,
        prompt_chars=len(text),
        estimated_tokens=count_text(text),
        prompt_tokens=result.prompt_tokens,
        found=ANSWER in result.content,
        prefill_rate=result.prompt_rate or 0.0,
        first_token_seconds=result.first_token_seconds,
        memory_bytes=entry.size if entry else 0,
        server_context=entry.context_length if entry else None,
    )

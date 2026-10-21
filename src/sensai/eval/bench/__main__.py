"""`python -m sensai.eval.bench <suite>`: run a benchmark, print it, save it.

Suites: perf (Sensai's code, no model), speed, tools, effort, context, rag.
Results go to `reports/bench/<suite>.json` and `.md`.
"""

import argparse
import asyncio
import json
import platform
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from sensai.eval.bench import context, models, perf, rag
from sensai.eval.bench.ollama import DEFAULT_URL, OllamaBench
from sensai.eval.bench.timing import human_seconds, table

ROOT = Path(__file__).resolve().parents[4]
SUITES = ("perf", "speed", "tools", "effort", "context", "rag")
DEFAULT_MODEL = "qwen3.5:4b"


def _gb(size: int) -> str:
    return f"{size / 1e9:.1f} GB" if size else "-"


def _rate(value: float) -> str:
    return f"{value:.1f}" if value else "-"


def machine() -> str:
    cpu = platform.processor() or platform.machine()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return f"{cpu}, Python {platform.python_version()}, {platform.system()}"


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


def save(out: Path, suite: str, markdown: str, data: Any) -> None:
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    header = f"# Benchmark: {suite}\n\n{stamp} · {machine()}\n\n"
    (out / f"{suite}.md").write_text(header + markdown + "\n", encoding="utf-8")
    (out / f"{suite}.json").write_text(
        json.dumps(
            {
                "suite": suite,
                "date": stamp,
                "machine": machine(),
                "results": _jsonable(data),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


def run_perf(args: argparse.Namespace) -> tuple[str, Any]:
    results = perf.run_perf(args.repeat, args.quick)
    return perf.perf_table(results), [
        {
            "area": r.group,
            "operation": r.name,
            "size": r.size,
            "median_s": r.stat.median,
            "best_s": r.stat.best,
        }
        for r in results
    ]


def _models(args: argparse.Namespace, client: OllamaBench) -> list[str]:
    if args.models:
        return args.models.split(",")
    return [name for name in client.installed() if "embed" not in name]


def run_speed(args: argparse.Namespace, client: OllamaBench) -> tuple[str, Any]:
    results = []
    for name in _models(args, client):
        print(f"  speed: {name}", file=sys.stderr)
        try:
            results.append(models.bench_speed(client, name, args.runs))
        except (RuntimeError, httpx.HTTPError) as exc:
            print(f"    skipped: {exc}", file=sys.stderr)
    client.unload_all()
    rows = [
        [
            r.model,
            r.parameters,
            r.quantization,
            _gb(r.memory_bytes),
            "GPU" if r.vram_bytes else "CPU",
            f"{r.load_seconds:.1f} s",
            _rate(r.prompt_rate),
            _rate(r.reply_rate),
            f"{r.first_token_seconds:.1f} s",
            f"{r.reply_seconds:.1f} s",
        ]
        for r in sorted(results, key=lambda r: -r.reply_rate)
    ]
    headers = [
        "model",
        "params",
        "quant",
        "memory",
        "runs on",
        "cold load",
        "prefill tok/s",
        "decode tok/s",
        "1st token",
        "reply (128 tok)",
    ]
    return table(headers, rows), results


def run_tools(args: argparse.Namespace, client: OllamaBench) -> tuple[str, Any]:
    results = []
    for name in _models(args, client):
        print(f"  tools: {name}", file=sys.stderr)
        results.append(models.bench_tools(client, name))
        client.unload(name)
    rows = [
        [
            r.model,
            f"{r.passed}/{r.total}",
            f"{r.accuracy:.0%}",
            r.false_calls,
            r.missed_calls,
            r.wrong_tool,
            f"{r.median_seconds:.1f} s",
        ]
        for r in sorted(results, key=lambda r: -r.accuracy)
    ]
    headers = [
        "model",
        "right",
        "accuracy",
        "tool for a plain question",
        "missed tool",
        "wrong tool/args",
        "median time",
    ]
    return table(headers, rows), results


def run_effort(args: argparse.Namespace, client: OllamaBench) -> tuple[str, Any]:
    results = []
    for name in args.models.split(",") if args.models else [DEFAULT_MODEL]:
        results.extend(models.bench_effort(client, name))
    rows = [
        [
            r.model,
            r.effort,
            "yes" if r.correct else "no",
            r.thinking_chars,
            r.reply_tokens,
            f"{r.seconds:.1f} s",
        ]
        for r in results
    ]
    headers = [
        "model",
        "think",
        "correct",
        "thinking chars",
        "tokens generated",
        "time",
    ]
    return table(headers, rows), results


def run_context(args: argparse.Namespace, client: OllamaBench) -> tuple[str, Any]:
    model = args.models.split(",")[0] if args.models else DEFAULT_MODEL
    sizes = tuple(int(s) for s in args.sizes.split(","))
    print(f"  context: {model} {sizes}", file=sys.stderr)
    scaling = context.bench_context(client, model, sizes)
    truncation = context.bench_truncation(client, model)
    client.unload_all()

    def row(r: context.ContextResult) -> list[Any]:
        return [
            r.num_ctx or "default",
            f"{r.depth:.0%}",
            r.estimated_tokens,
            r.prompt_tokens,
            "yes" if r.found else "NO",
            _rate(r.prefill_rate),
            f"{r.first_token_seconds:.1f} s",
            _gb(r.memory_bytes),
            r.server_context or "-",
        ]

    headers = [
        "num_ctx",
        "needle depth",
        "estimated tok",
        "real prompt tok",
        "found",
        "prefill tok/s",
        "1st token",
        "memory",
        "server ctx",
    ]
    text = (
        f"Model: {model}\n\n### Scaling\n\n"
        + table(headers, [row(r) for r in scaling])
        + "\n\n### Prompt over the default window\n\n"
        + table(headers, [row(r) for r in truncation])
    )
    return text, {"scaling": scaling, "truncation": truncation}


def run_rag(args: argparse.Namespace, client: OllamaBench) -> tuple[str, Any]:
    model = args.models.split(",")[0] if args.models else DEFAULT_MODEL
    questions = rag.load_questions(Path(args.questions))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    index, results = asyncio.run(
        rag.bench_rag(
            model,
            questions,
            ROOT / "data" / "collecte",
            ROOT / "personas" / "collecte.md",
            out / "rag-bench.db",
            args.base_url,
        )
    )
    client.unload_all()
    rows = [
        [
            r.condition,
            f"{r.accuracy:.0%}",
            f"{r.answered_right}/{r.answerable}",
            f"{r.refused_right}/{r.unanswerable}",
            f"{r.cited}/{r.answerable}",
            f"{r.median_seconds:.1f} s",
            f"{r.median_first_token:.1f} s",
            r.median_prompt_tokens,
        ]
        for r in results
    ]
    headers = [
        "condition",
        "accuracy",
        "facts right",
        "refusals right",
        "source cited",
        "median time",
        "1st token",
        "prompt tok",
    ]
    text = (
        f"Model: {model} · {len(questions)} questions · index: {index.chunks} chunks in "
        f"{human_seconds(index.seconds)}, one retrieval {human_seconds(index.retrieval_seconds)}"
        "\n\n" + table(headers, rows)
    )
    return text, {"index": index, "conditions": results}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sensai.eval.bench", description=__doc__
    )
    parser.add_argument("suite", choices=SUITES)
    parser.add_argument(
        "--models",
        default=None,
        help="Comma-separated models (default: all installed, or qwen3.5:4b)",
    )
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--out", default=str(ROOT / "reports" / "bench"))
    parser.add_argument("--repeat", type=int, default=5, help="perf: samples per case")
    parser.add_argument("--quick", action="store_true", help="perf: small sizes only")
    parser.add_argument(
        "--runs", type=int, default=3, help="speed: warm runs per model"
    )
    parser.add_argument(
        "--sizes", default="2048,4096,8192,16384,32768", help="context: num_ctx values"
    )
    parser.add_argument(
        "--questions", default=str(ROOT / "data" / "bench" / "rag-questions.jsonl")
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.suite == "perf":
            text, data = run_perf(args)
        else:
            client = OllamaBench(args.base_url)
            runner = {
                "speed": run_speed,
                "tools": run_tools,
                "effort": run_effort,
                "context": run_context,
                "rag": run_rag,
            }[args.suite]
            text, data = runner(args, client)
    except httpx.ConnectError:
        print(f"✗ Ollama is not reachable at {args.base_url}.", file=sys.stderr)
        return 2
    print(text)
    save(Path(args.out), args.suite, text, data)
    print(f"\nSaved to {args.out}/{args.suite}.md and .json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

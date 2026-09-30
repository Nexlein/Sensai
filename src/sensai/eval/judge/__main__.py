"""Grade replies from a JSONL file with a judge model.

    python -m sensai.eval.judge replies.jsonl [--provider ollama] [--model llama3.2]

Each line is {"question": ..., "answer": ..., "context": ...}; "context" is the
retrieved source text and may be left out.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from sensai.core.config import DEFAULT_MODEL, DEFAULT_PROVIDER
from sensai.domain.protocols import LLMProvider
from sensai.eval.judge.judge import LLMJudge
from sensai.eval.judge.models import JudgeInput
from sensai.providers import get_provider


def load_items(path: Path) -> list[JudgeInput]:
    items: list[JudgeInput] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            items.append(JudgeInput.model_validate(json.loads(line)))
        except (ValueError, ValidationError) as exc:
            raise ValueError(f"{path}:{number}: invalid line ({exc})") from exc
    return items


def main(
    argv: Sequence[str] | None = None,
    provider_factory: Callable[..., LLMProvider] = get_provider,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m sensai.eval.judge")
    parser.add_argument("file", type=Path, help="JSONL file of replies to grade")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)

    try:
        items = load_items(args.file)
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2

    provider: Any = provider_factory(args.provider, model=args.model)
    report = asyncio.run(LLMJudge(lambda: provider).judge_all(items))
    print(report.render())
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())

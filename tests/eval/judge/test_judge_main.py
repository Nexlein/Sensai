import json
from collections.abc import AsyncGenerator
from typing import Any

from sensai.domain.events import Event, TextChunkEvent
from sensai.domain.models import Message
from sensai.eval.judge.__main__ import load_items, main

SCORES = json.dumps({"relevance": 4, "coherence": 5})
CLAIMS = json.dumps(
    {
        "claims": [
            {"text": "a", "verdict": "supported"},
            {"text": "b", "verdict": "unsupported"},
            {"text": "c", "verdict": "contradicted"},
        ]
    }
)


class ScriptedProvider:
    """Answers each call with the next scripted reply."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)

    async def chat_stream(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[Event]:
        yield TextChunkEvent(content=self.replies.pop(0))


def _write(tmp_path, *rows: dict | str):
    path = tmp_path / "replies.jsonl"
    path.write_text(
        "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows),
        encoding="utf-8",
    )
    return path


def test_load_items_skips_blank_lines_and_defaults_context(tmp_path):
    path = _write(
        tmp_path, {"question": "q", "answer": "a"}, "", {"question": "q", "answer": "b"}
    )
    items = load_items(path)
    assert [i.answer for i in items] == ["a", "b"]
    assert items[0].context == ""


def test_main_prints_the_report_and_exits_zero(tmp_path, capsys):
    path = _write(tmp_path, {"question": "q", "answer": "a", "context": "c"})
    provider = ScriptedProvider(SCORES, CLAIMS)

    code = main([str(path)], provider_factory=lambda name, **cfg: provider)

    assert code == 0
    out = capsys.readouterr().out
    assert "replies judged: 1 (0 with errors)" in out
    assert "unverifiable statements: 2" in out


def test_main_exits_one_when_the_judge_failed(tmp_path, capsys):
    path = _write(tmp_path, {"question": "q", "answer": "a"})
    provider = ScriptedProvider("x", "y", "z")

    assert main([str(path)], provider_factory=lambda name, **cfg: provider) == 1
    assert "error:" in capsys.readouterr().out


def test_main_passes_provider_and_model_to_the_factory(tmp_path):
    path = _write(tmp_path, {"question": "q", "answer": "a"})
    seen = {}

    def factory(name, **cfg):
        seen.update(name=name, **cfg)
        return ScriptedProvider(SCORES)

    main([str(path), "--provider", "mock", "--model", "m1"], provider_factory=factory)
    assert seen == {"name": "mock", "model": "m1"}


def test_main_reports_a_malformed_line_with_its_number(tmp_path, capsys):
    path = _write(tmp_path, {"question": "q", "answer": "a"}, "{oops")
    assert main([str(path)]) == 2
    assert f"{path}:2: invalid line" in capsys.readouterr().err


def test_main_reports_a_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "nope.jsonl")]) == 2
    assert "nope.jsonl" in capsys.readouterr().err

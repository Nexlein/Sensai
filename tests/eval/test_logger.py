import json
from pathlib import Path

import pytest

from sensai.eval.logger import TurnLogger


def _read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_disabled_by_default_writes_nothing(tmp_path):
    logger = TurnLogger(path=tmp_path / "turns.jsonl")

    logger.log("llama3.2", 12.5, prompt_tokens=10, completion_tokens=5)

    assert not logger.path.exists()


def test_log_writes_one_valid_json_line(tmp_path):
    logger = TurnLogger(path=tmp_path / "turns.jsonl", enabled=True)

    logger.log("llama3.2", 12.5, prompt_tokens=10, completion_tokens=5)

    lines = _read_lines(logger.path)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["model"] == "llama3.2"
    assert entry["latency_ms"] == 12.5
    assert entry["prompt_tokens"] == 10
    assert entry["completion_tokens"] == 5
    assert "error" not in entry
    assert "timestamp" in entry


def test_log_with_error_field(tmp_path):
    logger = TurnLogger(path=tmp_path / "turns.jsonl", enabled=True)

    logger.log("llama3.2", 3.0, error="boom")

    entry = _read_lines(logger.path)[0]
    assert entry["error"] == "boom"
    assert entry["prompt_tokens"] is None
    assert entry["completion_tokens"] is None


def test_log_failure_never_raises(tmp_path, monkeypatch):
    logger = TurnLogger(path=tmp_path / "missing" / "turns.jsonl", enabled=True)

    def _raise(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr(Path, "mkdir", _raise)

    logger.log("llama3.2", 1.0)


def test_track_success_logs_usage(tmp_path):
    logger = TurnLogger(path=tmp_path / "turns.jsonl", enabled=True)

    with logger.track("llama3.2") as usage:
        usage["prompt_tokens"] = 20
        usage["completion_tokens"] = 8

    entry = _read_lines(logger.path)[0]
    assert entry["prompt_tokens"] == 20
    assert entry["completion_tokens"] == 8
    assert "error" not in entry


def test_track_failure_logs_error_and_reraises(tmp_path):
    logger = TurnLogger(path=tmp_path / "turns.jsonl", enabled=True)

    with pytest.raises(ValueError), logger.track("llama3.2"):
        raise ValueError("turn failed")

    entry = _read_lines(logger.path)[0]
    assert entry["error"] == "turn failed"
    assert entry["prompt_tokens"] is None

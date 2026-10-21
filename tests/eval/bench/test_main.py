"""`python -m sensai.eval.bench`: suites, saved reports, Ollama down."""

import json

import httpx

from sensai.eval.bench import __main__ as bench
from sensai.eval.bench.perf import PerfResult
from sensai.eval.bench.timing import Stat


def test_perf_suite_prints_and_saves_markdown_and_json(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        bench.perf,
        "run_perf",
        lambda repeat, quick: [PerfResult("a", "op", "-", Stat((0.5,)))],
    )

    assert bench.main(["perf", "--out", str(tmp_path)]) == 0

    assert "| a " in capsys.readouterr().out
    assert (tmp_path / "perf.md").read_text().startswith("# Benchmark: perf")
    data = json.loads((tmp_path / "perf.json").read_text())
    assert data["results"][0]["median_s"] == 0.5


def test_unreachable_ollama_is_one_line_and_exit_2(monkeypatch, tmp_path, capsys):
    def refuse(args, client):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(bench, "run_speed", refuse)

    assert bench.main(["speed", "--out", str(tmp_path)]) == 2
    assert "Ollama is not reachable" in capsys.readouterr().err


def test_machine_names_the_cpu():
    assert "Python" in bench.machine()

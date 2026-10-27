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


def test_results_nested_in_a_dict_are_saved_as_json_objects(tmp_path):
    stat = Stat(runs=(1.0, 0.5))

    bench.save(tmp_path, "context", "# x", {"scaling": [stat], "pair": (stat,)})

    results = json.loads((tmp_path / "context.json").read_text())["results"]
    assert results["scaling"][0]["runs"] == [1.0, 0.5]
    assert results["pair"][0]["runs"] == [1.0, 0.5]


def test_speed_saves_completed_model_before_next_one_fails(tmp_path, monkeypatch):
    from sensai.eval.bench.models import bench_speed

    from .fake_ollama import FakeOllama

    monkeypatch.setattr(bench.models, "nvidia_vram_bytes", lambda: None)
    client = FakeOllama().client()
    completed = bench_speed(client, "a", runs=3)

    def measure(client, name, runs):
        if name == "b":
            raise RuntimeError("model unavailable")
        return completed

    monkeypatch.setattr(bench.models, "bench_speed", measure)
    args = bench.build_parser().parse_args(
        ["speed", "--models", "a,b", "--out", str(tmp_path)]
    )
    markdown, results = bench.run_speed(args, client)
    checkpoint = json.loads((tmp_path / "models" / "a.json").read_text())
    assert checkpoint["results"]["model"] == "a"
    assert len(checkpoint["results"]["samples"]) == 4
    assert results == [completed]
    assert "VRAM (Ollama)" in markdown


def test_french_cli_saves_exact_replies_and_model_checkpoint(monkeypatch, tmp_path):
    from .fake_ollama import FakeOllama, answer

    fake = FakeOllama(lambda payload: answer("Réponse.\nDétail conservé."))
    monkeypatch.setattr(bench, "OllamaBench", lambda *args: fake.client())
    assert bench.main(["french", "--models", "m", "--out", str(tmp_path)]) == 0
    results = json.loads((tmp_path / "french.json").read_text())["results"]
    assert len(results) == 6
    assert results[0]["answer"] == "Réponse.\nDétail conservé."
    assert "Détail conservé." in (tmp_path / "french.md").read_text()
    assert (tmp_path / "models" / "m.json").exists()

"""Component benchmark: every case runs and is reported."""

from sensai.eval.bench import perf


def test_quick_run_measures_every_area(monkeypatch):
    monkeypatch.setattr(perf, "_startup", lambda repeat: perf.Stat((0.1,)))

    results = perf.run_perf(repeat=1, quick=True)

    areas = {result.group for result in results}
    assert {
        "startup",
        "guardrails",
        "engine",
        "prompt",
        "tools",
        "memory",
        "rag",
        "config",
    } <= areas
    assert all(result.stat.median >= 0 for result in results)
    text = perf.perf_table(results)
    assert text.splitlines()[0].startswith("| area")
    assert "vector search" in text

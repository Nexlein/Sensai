"""Model benchmarks: speed, tool choice, thinking effort."""

import subprocess
from types import SimpleNamespace

import pytest

from sensai.eval.bench.models import (
    TOOL_CASES,
    ToolCase,
    bench_effort,
    bench_french,
    bench_speed,
    bench_tools,
    judge_tool_case,
    normalize,
    nvidia_vram_bytes,
    think_off,
    tool_schemas,
)
from sensai.eval.bench.ollama import Loaded

from .fake_ollama import FakeOllama, answer


@pytest.fixture(autouse=True)
def no_live_gpu_query(monkeypatch):
    monkeypatch.setattr(
        "sensai.eval.bench.models.subprocess.run",
        lambda *a, **k: SimpleNamespace(stdout=""),
    )


def test_nvidia_vram_counts_only_ollama_processes(monkeypatch):
    monkeypatch.setattr(
        "sensai.eval.bench.models.subprocess.run",
        lambda *a, **k: SimpleNamespace(
            stdout="/usr/bin/ollama, 3000\nother, 200\n/usr/bin/ollama, 12\n"
        ),
    )
    assert nvidia_vram_bytes() == 3012 * 1024 * 1024


@pytest.mark.parametrize(
    "error", [FileNotFoundError(), subprocess.TimeoutExpired("nvidia-smi", 5)]
)
def test_nvidia_vram_unavailable_is_not_reported_as_zero(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("sensai.eval.bench.models.subprocess.run", fail)
    assert nvidia_vram_bytes() is None


def test_normalize_drops_case_accents_and_extra_spaces():
    assert normalize("Été  À\nPARIS") == "ete a paris"


def test_thinking_is_turned_off_only_for_models_that_think():
    assert think_off(FakeOllama().client(), "m") is False
    assert think_off(FakeOllama(capabilities=["completion"]).client(), "m") is None


def test_speed_unloads_first_then_measures_cold_and_warm_calls():
    fake = FakeOllama()

    result = bench_speed(fake.client(), "m", runs=3)

    chats = fake.chats()
    assert [p for p, _ in fake.requests][:2] == ["/api/show", "/api/ps"]
    assert len(chats) == 4
    assert len({c["messages"][0]["content"] for c in chats}) == 4
    assert all(
        c["options"]["seed"] == 42 and c["options"]["temperature"] == 0 for c in chats
    )
    assert result.load_seconds == 1.0
    assert result.reply_rate == 25.0
    assert result.memory_bytes == 3_000_000_000
    assert result.quantization == "Q4_K_M"
    assert all(c["stream"] and c["options"]["num_ctx"] == 8192 for c in chats)


def test_tool_schemas_are_sensais_default_tools():
    names = {schema["function"]["name"] for schema in tool_schemas()}

    assert {"read_file", "list_dir", "write_file", "web_search", "run_python"} <= names


def test_speed_resolves_latest_alias_for_memory_counters(monkeypatch):
    client = FakeOllama().client()
    monkeypatch.setattr(client, "loaded", lambda: [Loaded("m:latest", 10, 8, 8192)])
    result = bench_speed(client, "m")
    assert (result.memory_bytes, result.vram_bytes) == (10, 8)


def test_remote_benchmark_does_not_use_local_gpu_memory(monkeypatch):
    def forbid():
        pytest.fail("remote Ollama must not use the local GPU counters")

    monkeypatch.setattr("sensai.eval.bench.models.nvidia_vram_bytes", forbid)
    result = bench_speed(FakeOllama().client(), "m")
    assert result.nvidia_vram_bytes is None


def test_speed_does_not_present_missing_memory_counters_as_cpu(monkeypatch):
    client = FakeOllama().client()
    monkeypatch.setattr(client, "loaded", list)
    with pytest.raises(RuntimeError, match="No loaded memory counters"):
        bench_speed(client, "m")


def _result(tool=None, arguments=None):
    import httpx

    from sensai.eval.bench.ollama import OllamaBench

    payload = (
        answer("", tool=tool, arguments=arguments or {}) if tool else answer("texte")
    )
    client = OllamaBench(
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
            base_url="http://x",
        )
    )
    return client.chat("m", [])


def test_judge_tool_case_names_each_kind_of_mistake():
    plain = ToolCase("Bonjour", None)
    read = ToolCase("Lis a.md", "read_file", ("path", "a.md"))

    assert judge_tool_case(plain, _result()) == "ok"
    assert judge_tool_case(plain, _result("list_dir")) == "false_call"
    assert judge_tool_case(read, _result()) == "missed"
    assert judge_tool_case(read, _result("list_dir")) == "wrong_tool"
    assert judge_tool_case(read, _result("read_file", {"path": "b.md"})) == "bad_args"
    assert judge_tool_case(read, _result("read_file", {"path": "docs/a.md"})) == "ok"


def test_tools_benchmark_scores_every_case():
    def reply(payload):
        prompt = payload["messages"][-1]["content"]
        case = next(c for c in TOOL_CASES if c.prompt == prompt)
        if case.expected is None:
            return answer("réponse")
        arguments = {case.argument[0]: case.argument[1]} if case.argument else {}
        return answer("", tool=case.expected, arguments=arguments)

    fake = FakeOllama(reply)
    result = bench_tools(fake.client(), "m")

    assert (result.passed, result.total) == (len(TOOL_CASES), len(TOOL_CASES))
    assert result.accuracy == 1.0
    assert fake.chats()[0]["messages"][0]["role"] == "system"
    assert fake.chats()[0]["tools"]


def test_models_without_tools_are_reported_not_called():
    fake = FakeOllama(capabilities=["completion"])

    result = bench_tools(fake.client(), "m")

    assert result.passed == 0
    assert fake.chats() == []


def test_effort_runs_each_level_and_checks_the_answer():
    fake = FakeOllama(lambda payload: answer("200 km"))

    results = bench_effort(fake.client(), "m", levels=(False, "high"))

    assert [r.effort for r in results] == ["off", "high"]
    assert all(r.correct for r in results)
    assert [c["think"] for c in fake.chats()] == [False, "high"]


def test_french_retains_exact_answers_and_uses_the_same_settings_for_every_task():
    fake = FakeOllama(lambda payload: answer("Réponse française.\nDeuxième ligne."))
    results = bench_french(fake.client(), "m")
    assert len(results) == 6
    assert len({r["case"] for r in results}) == 6
    assert all(r["answer"] == "Réponse française.\nDeuxième ligne." for r in results)
    assert all(not r["possible_truncation"] for r in results)
    assert all(c["think"] is False for c in fake.chats())
    assert all(
        c["options"]
        == {
            "temperature": 0,
            "seed": 42,
            "num_ctx": 8192,
            "num_predict": 512,
        }
        for c in fake.chats()
    )


def test_french_flags_answers_that_may_have_hit_the_output_limit():
    fake = FakeOllama(lambda payload: answer("texte", reply_tokens=512))
    assert all(r["possible_truncation"] for r in bench_french(fake.client(), "m"))

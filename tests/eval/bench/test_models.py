"""Model benchmarks: speed, tool choice, thinking effort."""

from sensai.eval.bench.models import (
    TOOL_CASES,
    ToolCase,
    bench_effort,
    bench_speed,
    bench_tools,
    judge_tool_case,
    normalize,
    think_off,
    tool_schemas,
)

from .fake_ollama import FakeOllama, answer


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


def test_tool_schemas_are_sensais_default_tools():
    names = {schema["function"]["name"] for schema in tool_schemas()}

    assert {"read_file", "list_dir", "write_file", "web_search", "run_python"} <= names


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

"""Benchmark Ollama client: counters, memory, unloading."""

import json
from types import SimpleNamespace

import httpx
import pytest

from sensai.eval.bench.ollama import OllamaBench

from .fake_ollama import FakeOllama, answer


def test_stream_measures_first_visible_text_and_keeps_final_counters(monkeypatch):
    ticks = iter([10.0, 10.75, 13.0])
    monkeypatch.setattr(
        "sensai.eval.bench.ollama.time",
        SimpleNamespace(perf_counter=lambda: next(ticks)),
    )
    chunks = [
        {"message": {"content": ""}},
        {"message": {"thinking": "hmm"}},
        {"message": {"content": "bon"}},
        {"message": {"content": "jour"}},
        {**answer(""), "message": {}},
    ]
    client = OllamaBench(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, text="\n".join(json.dumps(c) for c in chunks)
                )
            ),
            base_url="http://x",
        )
    )
    result = client.chat("m", [], stream=True)
    assert result.content == "bonjour"
    assert result.thinking == "hmm"
    assert result.first_token_seconds == 0.75
    assert result.wall_seconds == 3.0
    assert result.reply_tokens == 50


@pytest.mark.parametrize(
    "chunks, error",
    [
        ([{"error": "broken"}], "broken"),
        ([{"message": {"content": "hi"}}], "final counters"),
        ([answer("")], "no answer text"),
    ],
)
def test_stream_rejects_failed_or_incomplete_measurements(chunks, error):
    client = OllamaBench(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, text="\n".join(json.dumps(c) for c in chunks)
                )
            ),
            base_url="http://x",
        )
    )
    with pytest.raises(RuntimeError, match=error):
        client.chat("m", [], stream=True)


def test_chat_keeps_the_server_counters_in_seconds():
    fake = FakeOllama(
        lambda payload: answer("salut", prompt_tokens=200, reply_tokens=40)
    )

    result = fake.client().chat(
        "m", [{"role": "user", "content": "hi"}], {"seed": 1}, False
    )

    assert result.content == "salut"
    assert result.prompt_rate == pytest.approx(400)
    assert result.reply_rate == pytest.approx(20)
    assert result.first_token_seconds == pytest.approx(1.5)
    assert fake.chats()[0] == {
        "model": "m",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "options": {"seed": 1},
        "think": False,
    }


def test_chat_lists_called_tools():
    fake = FakeOllama(lambda payload: answer("", tool="read_file"))

    assert fake.client().chat("m", []).tool_names == ["read_file"]


def test_chat_error_is_a_runtime_error():
    import httpx

    from sensai.eval.bench.ollama import OllamaBench

    client = OllamaBench(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(400, text="no think")
            ),
            base_url="http://x",
        )
    )

    with pytest.raises(RuntimeError, match="400"):
        client.chat("m", [])


def test_loaded_unload_installed_capabilities_and_embed():
    fake = FakeOllama(capabilities=["completion"])
    client = fake.client()
    client.chat("m", [])

    assert [m.name for m in client.loaded()] == ["m"]
    assert client.loaded()[0].details["quantization_level"] == "Q4_K_M"
    client.unload_all()
    assert client.loaded() == []
    assert client.installed() == ["a", "b"]
    assert client.capabilities("m") == ["completion"]
    client.capabilities("m")
    assert [p for p, _ in fake.requests].count("/api/show") == 1
    vectors, seconds = client.embed("e", ["x", "y"])
    assert vectors == [[1.0, 0.0], [1.0, 0.0]]
    assert seconds >= 0

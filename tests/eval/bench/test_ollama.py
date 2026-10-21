"""Benchmark Ollama client: counters, memory, unloading."""

import pytest

from .fake_ollama import FakeOllama, answer


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

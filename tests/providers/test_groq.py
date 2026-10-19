import json

import httpx
import pytest

from sensai.domain.errors import ProviderError
from sensai.domain.events import TextChunkEvent, ToolCallEvent, UsageEvent
from sensai.domain.models import Message, ToolCall
from sensai.providers.groq import GroqLLMProvider


def _sse(*chunks: dict | str) -> str:
    return "".join(
        f"data: {c if isinstance(c, str) else json.dumps(c)}\n\n" for c in chunks
    )


def _delta(**delta) -> dict:
    return {"choices": [{"index": 0, "delta": delta}]}


def _provider(handler) -> GroqLLMProvider:
    provider = GroqLLMProvider(api_key="gsk_test")
    transport = httpx.MockTransport(handler)
    headers = {"Authorization": "Bearer gsk_test"}

    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=provider.base_url,
            timeout=provider.timeout,
            headers=headers,
            transport=transport,
        )

    provider._get_client = _get_client
    return provider


async def _collect(provider: GroqLLMProvider, tools=None) -> list:
    return [
        e
        async for e in provider.chat_stream([Message(role="user", content="hi")], tools)
    ]


def test_missing_api_key_raises_provider_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="API key"):
        GroqLLMProvider()


def test_api_key_falls_back_to_environment(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_env")
    assert GroqLLMProvider()._api_key == "gsk_env"


def test_explicit_api_key_beats_environment(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_env")
    assert GroqLLMProvider(api_key="gsk_cfg")._api_key == "gsk_cfg"


def test_format_message_with_tool_calls_serializes_arguments():
    provider = GroqLLMProvider(api_key="k")
    msg = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="call_1", name="search", arguments={"q": "x"})],
    )
    assert provider._format_message(msg)["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "search", "arguments": '{"q": "x"}'},
        }
    ]


def test_format_messages_links_tool_results_to_call_ids_in_order():
    provider = GroqLLMProvider(api_key="k")
    messages = [
        Message(role="user", content="inspect"),
        Message(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id="a", name="list_dir", arguments={}),
                ToolCall(id="b", name="read_file", arguments={}),
            ],
        ),
        Message(role="tool", content="one"),
        Message(role="tool", content="two"),
        Message(role="assistant", content="done"),
    ]
    payloads = provider._format_messages(messages)
    assert payloads[2]["tool_call_id"] == "a"
    assert payloads[3]["tool_call_id"] == "b"
    assert "tool_call_id" not in payloads[4]


async def test_streams_text_chunks_and_stops_at_done():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/openai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer gsk_test"
        assert body["stream"] is True
        assert "tools" not in body
        return httpx.Response(
            200,
            text=_sse(
                _delta(role="assistant", content=""),
                _delta(content="Hel"),
                _delta(content="lo"),
                "[DONE]",
                _delta(content="ignored"),
            ),
        )

    events = await _collect(_provider(handler))
    assert events == [
        TextChunkEvent(content="Hel", timestamp=events[0].timestamp),
        TextChunkEvent(content="lo", timestamp=events[1].timestamp),
    ]


async def test_reassembles_fragmented_tool_calls_by_index():
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["tools"] == [{"type": "function"}]
        return httpx.Response(
            200,
            text=_sse(
                _delta(
                    tool_calls=[
                        {
                            "index": 0,
                            "id": "x",
                            "function": {"name": "read_file", "arguments": ""},
                        },
                        {"index": 1, "function": {"name": "list_dir"}},
                    ]
                ),
                _delta(
                    tool_calls=[{"index": 0, "function": {"arguments": '{"path": '}}]
                ),
                _delta(
                    tool_calls=[{"index": 0, "function": {"arguments": '"a.txt"}'}}]
                ),
                "[DONE]",
            ),
        )

    events = await _collect(_provider(handler), tools=[{"type": "function"}])
    assert [(e.tool_name, e.arguments) for e in events] == [
        ("read_file", {"path": "a.txt"}),
        ("list_dir", {}),
    ]
    assert all(isinstance(e, ToolCallEvent) for e in events)


async def test_malformed_tool_arguments_raise_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=_sse(
                _delta(
                    tool_calls=[
                        {"index": 0, "function": {"name": "t", "arguments": "{oops"}}
                    ]
                ),
                "[DONE]",
            ),
        )

    with pytest.raises(ProviderError, match="malformed arguments"):
        await _collect(_provider(handler))


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, {"error": {"message": "bad key"}}, "rejected the API key"),
        (429, {"error": {"message": "slow down"}}, "rate limit"),
        (
            404,
            {"error": {"message": "model not found"}},
            r"\[404\]: model not found",
        ),
    ],
)
async def test_http_errors_become_provider_errors(status, body, expected):
    provider = _provider(lambda request: httpx.Response(status, json=body))
    with pytest.raises(ProviderError, match=expected):
        await _collect(provider)


async def test_rate_limit_error_shows_groq_detail_and_retry_after():
    provider = _provider(
        lambda request: httpx.Response(
            429,
            json={"error": {"message": "Limit 8000 TPM, try again in 7s"}},
            headers={"retry-after": "7"},
        )
    )
    with pytest.raises(ProviderError) as raised:
        await _collect(provider)

    assert "Limit 8000 TPM" in str(raised.value)
    assert "Retry in 7s" in str(raised.value)


async def test_http_error_without_json_body_uses_raw_text():
    provider = _provider(lambda request: httpx.Response(502, text="bad gateway"))
    with pytest.raises(ProviderError, match="bad gateway"):
        await _collect(provider)


async def test_mid_stream_error_chunk_raises_provider_error():
    provider = _provider(
        lambda request: httpx.Response(
            200, text=_sse(_delta(content="a"), {"error": {"message": "overloaded"}})
        )
    )
    with pytest.raises(ProviderError, match="overloaded"):
        await _collect(provider)


async def test_timeout_and_connection_errors_become_provider_errors():
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(ProviderError, match="timed out"):
        await _collect(_provider(timeout))
    with pytest.raises(ProviderError, match="Could not reach Groq"):
        await _collect(_provider(refused))


async def test_unreadable_stream_raises_provider_error():
    provider = _provider(
        lambda request: httpx.Response(200, text="data: {not json\n\n")
    )
    with pytest.raises(ProviderError, match="unreadable"):
        await _collect(provider)


async def test_final_chunk_usage_becomes_a_usage_event():
    usage = {
        "prompt_tokens": 50,
        "completion_tokens": 20,
        "prompt_time": 0.01,
        "completion_time": 0.08,
        "total_time": 0.09,
    }
    provider = _provider(
        lambda request: httpx.Response(
            200,
            text=_sse(
                _delta(content="hi"),
                {"choices": [], "x_groq": {"usage": usage}},
                "[DONE]",
            ),
        )
    )

    events = await _collect(provider)

    assert isinstance(events[-1], UsageEvent)
    assert (events[-1].prompt_tokens, events[-1].reply_tokens) == (50, 20)
    assert events[-1].reply_rate == pytest.approx(250.0)
    assert events[-1].total_seconds == 0.09


async def test_no_usage_event_when_groq_sends_no_counters():
    provider = _provider(
        lambda request: httpx.Response(200, text=_sse(_delta(content="hi"), "[DONE]"))
    )

    assert not any(isinstance(e, UsageEvent) for e in await _collect(provider))

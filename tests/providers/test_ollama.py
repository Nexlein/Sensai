import json
import os

import httpx
import pytest

from sensai.domain.events import TextChunkEvent, ToolCallEvent
from sensai.domain.models import Message, ToolCall
from sensai.providers.ollama import OllamaLLMProvider


def _lines_response(lines: list[dict], status_code: int = 200) -> httpx.MockTransport:
    body = "\n".join(json.dumps(line) for line in lines)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body)

    return httpx.MockTransport(handler)


def _patch_client(provider: OllamaLLMProvider, transport: httpx.MockTransport) -> None:
    def _get_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=provider.base_url, timeout=provider.timeout, transport=transport
        )

    provider._get_client = _get_client


def test_format_message_without_tool_calls():
    provider = OllamaLLMProvider()
    msg = Message(role="user", content="hi")
    assert provider._format_message(msg) == {"role": "user", "content": "hi"}


def test_format_message_with_tool_calls():
    provider = OllamaLLMProvider()
    msg = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(name="search", arguments={"q": "x"})],
    )
    payload = provider._format_message(msg)
    assert payload["tool_calls"] == [
        {"function": {"name": "search", "arguments": {"q": "x"}}}
    ]


def test_format_messages_names_tool_results_in_call_order():
    provider = OllamaLLMProvider()
    messages = [
        Message(role="user", content="inspect"),
        Message(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(name="list_dir", arguments={"path": "."}),
                ToolCall(name="read_file", arguments={"path": "AGENTS.md"}),
            ],
        ),
        Message(role="tool", content="AGENTS.md"),
        Message(role="tool", content="# AGENTS"),
        Message(role="assistant", content="done"),
    ]
    payloads = provider._format_messages(messages)
    assert payloads[2] == {
        "role": "tool",
        "content": "AGENTS.md",
        "tool_name": "list_dir",
    }
    assert payloads[3] == {
        "role": "tool",
        "content": "# AGENTS",
        "tool_name": "read_file",
    }
    assert "tool_name" not in payloads[4]


def test_parse_line_text_content():
    provider = OllamaLLMProvider()
    line = json.dumps({"message": {"content": "hello"}})
    events = provider._parse_line(line)
    assert len(events) == 1
    assert isinstance(events[0], TextChunkEvent)
    assert events[0].content == "hello"


def test_parse_line_tool_calls():
    provider = OllamaLLMProvider()
    line = json.dumps(
        {
            "message": {
                "tool_calls": [
                    {"function": {"name": "search", "arguments": {"q": "x"}}}
                ]
            }
        }
    )
    events = provider._parse_line(line)
    assert len(events) == 1
    assert isinstance(events[0], ToolCallEvent)
    assert events[0].tool_name == "search"
    assert events[0].arguments == {"q": "x"}


def test_parse_line_empty_content_yields_no_text_event():
    provider = OllamaLLMProvider()
    line = json.dumps({"message": {"content": ""}})
    assert provider._parse_line(line) == []


async def test_chat_stream_yields_text_chunks():
    provider = OllamaLLMProvider(model="llama3.2")
    transport = _lines_response(
        [
            {"message": {"content": "Hello"}},
            {"message": {"content": " world"}},
        ]
    )
    _patch_client(provider, transport)

    msg = Message(role="user", content="hi")
    events = [e async for e in provider.chat_stream(messages=[msg])]

    assert [e.content for e in events] == ["Hello", " world"]


async def test_chat_stream_yields_tool_call_then_text():
    provider = OllamaLLMProvider()
    transport = _lines_response(
        [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "search", "arguments": {"q": "x"}}}
                    ],
                    "content": "using tool",
                }
            }
        ]
    )
    _patch_client(provider, transport)

    events = [e async for e in provider.chat_stream(messages=[])]

    assert isinstance(events[0], ToolCallEvent)
    assert events[0].tool_name == "search"
    assert isinstance(events[1], TextChunkEvent)
    assert events[1].content == "using tool"


async def test_chat_stream_raises_on_http_error():
    provider = OllamaLLMProvider()
    transport = _lines_response([], status_code=500)
    _patch_client(provider, transport)

    with pytest.raises(RuntimeError, match="500"):
        async for _ in provider.chat_stream(messages=[]):
            pass


async def test_chat_stream_includes_tools_in_payload_when_given():
    provider = OllamaLLMProvider()
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, text="")

    transport = httpx.MockTransport(handler)
    _patch_client(provider, transport)

    tools = [{"type": "function", "function": {"name": "search"}}]
    async for _ in provider.chat_stream(messages=[], tools=tools):
        pass

    assert captured["body"]["tools"] == tools
    assert captured["body"]["stream"] is True


async def test_chat_stream_omits_tools_key_when_not_given():
    provider = OllamaLLMProvider()
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, text="")

    transport = httpx.MockTransport(handler)
    _patch_client(provider, transport)

    async for _ in provider.chat_stream(messages=[]):
        pass

    assert "tools" not in captured["body"]


async def test_embedding_provider_calls_embed_endpoint():
    from sensai.providers.ollama import OllamaEmbeddingProvider

    provider = OllamaEmbeddingProvider(model="nomic-embed-text")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0], [0.0, 1.0]]})

    _patch_client(provider, httpx.MockTransport(handler))
    vectors = await provider.embed_texts(["first", "second"])

    assert captured["path"] == "/api/embed"
    assert captured["body"] == {
        "model": "nomic-embed-text",
        "input": ["first", "second"],
    }
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]


@pytest.fixture
def live_ollama_provider():
    """Opt-in model/template checks; normal unit tests require no Ollama server."""
    model = os.environ.get("SENSAI_OLLAMA_TEST_MODEL")
    if not model:
        pytest.skip("Set SENSAI_OLLAMA_TEST_MODEL to test a real local model")
    return OllamaLLMProvider(model=model)


@pytest.mark.parametrize(
    "prompt, expects_tool",
    [
        ("bonjour", False),
        ("hey", False),
        ("Explique-moi une boucle for en Python.", False),
        ("Recherche sur le web les dernières actualités de Python.", True),
        ("Cherche la météo actuelle à Paris sur internet.", True),
    ],
)
async def test_live_tool_selection(live_ollama_provider, prompt, expects_tool):
    from sensai.tools.registry import build_default_registry

    tools = build_default_registry(None).get_tools_schema()
    events = [
        event
        async for event in live_ollama_provider.chat_stream(
            [Message(role="user", content=prompt)], tools=tools
        )
    ]
    calls = [event for event in events if isinstance(event, ToolCallEvent)]
    text = "".join(
        event.content for event in events if isinstance(event, TextChunkEvent)
    )
    if expects_tool:
        assert len(calls) == 1
        assert calls[0].tool_name == "web_search"
        assert isinstance(calls[0].arguments.get("query"), str)
        assert calls[0].arguments["query"].strip()
    else:
        assert not calls
        assert text.strip()
        assert '"name"' not in text  # No unparsed/invented function call.


@pytest.mark.parametrize("approved", [True, False])
async def test_live_confirmation_round_trip(live_ollama_provider, approved):
    from sensai.core.engine import ChatEngine
    from sensai.domain.models import Conversation
    from sensai.tools.registry import ToolRegistry
    from sensai.tools.web import WebSearch

    executions = []
    confirmations = []

    class SearchFixture(WebSearch):
        requires_confirmation = True

        async def execute(self, **kwargs):
            executions.append(kwargs)
            return "Résultat de test : Python propose une documentation officielle sur https://docs.python.org/3/."

    registry = ToolRegistry()
    registry.register(SearchFixture("http://localhost:8888"))
    engine = ChatEngine(live_ollama_provider, Conversation(), registry)

    async def confirm(tc):
        confirmations.append(tc)
        return approved

    events = [
        event
        async for event in engine.send(
            "Recherche sur le web les dernières actualités de Python.",
            confirm_tool=confirm,
        )
    ]
    assert confirmations
    assert len(executions) == (len(confirmations) if approved else 0)
    assert any(isinstance(event, TextChunkEvent) for event in events)
    assert engine.conversation.messages[-1].role == "assistant"
    if not approved:
        assert engine.conversation.messages[-1].content == (
            "I didn't run the requested tool: web_search."
        )

    events = [event async for event in engine.send("bonjour", confirm_tool=confirm)]
    assert len(confirmations) == (len(executions) if approved else 1)
    assert not any(isinstance(event, ToolCallEvent) for event in events)
    assert any(isinstance(event, TextChunkEvent) for event in events)


async def test_live_file_read_uses_listing_then_exact_case(
    live_ollama_provider, tmp_path
):
    from sensai.core.engine import ChatEngine
    from sensai.domain.models import Conversation
    from sensai.tools.registry import build_default_registry

    sentinel = "SENSAI_FILE_CONTENT_4729"
    (tmp_path / "NOTES.md").write_text(sentinel, encoding="utf-8")
    registry = build_default_registry(str(tmp_path))
    engine = ChatEngine(live_ollama_provider, Conversation(), registry)
    events = [
        event
        async for event in engine.send(
            "Lis le fichier notes.md dans le dossier racine."
        )
    ]
    calls = [event for event in events if isinstance(event, ToolCallEvent)]
    assert calls
    assert calls[-1].tool_name == "read_file"
    assert calls[-1].arguments["path"].casefold() == "notes.md"
    if any(call.tool_name == "list_dir" for call in calls):
        assert calls[0].tool_name == "list_dir"
        assert calls[0].arguments["path"] == "."
    assert sentinel in engine.conversation.messages[-1].content

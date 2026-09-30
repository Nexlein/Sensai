import httpx
import pytest

from sensai.tools.web import WebSearch


def _mock_client(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("sensai.tools.web.httpx.AsyncClient", client)


def test_web_search_requires_base_url():
    with pytest.raises(ValueError, match="base_url"):
        WebSearch("   ")


@pytest.mark.parametrize("query", [None, "", "   ", 42])
async def test_web_search_rejects_invalid_query_without_request(monkeypatch, query):
    def unexpected_request(request):
        pytest.fail(f"Unexpected request to {request.url}")

    _mock_client(monkeypatch, unexpected_request)

    assert await WebSearch("http://localhost:8888").execute(query=query) == (
        "Error: query must be a non-empty string"
    )


async def test_web_search_requests_json_and_formats_up_to_five_results(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": f"Page {index}",
                        "url": f"https://example.org/{index}",
                        "content": f"Excerpt {index}",
                    }
                    for index in range(6)
                ]
            },
        )

    _mock_client(monkeypatch, handler)
    result = await WebSearch(" http://localhost:8888/ ").execute(query="  Ollama  ")

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/search"
    assert dict(requests[0].url.params) == {"q": "Ollama", "format": "json"}
    assert "Page 0\nURL: https://example.org/0\nExtrait: Excerpt 0" in result
    assert "Page 4" in result
    assert "Page 5" not in result


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"results": []}, "Aucun résultat trouvé."),
        (
            {"results": [{"title": "Untitled", "url": ""}]},
            "Aucun résultat trouvé.",
        ),
        (
            {"results": [{"title": "Page", "url": "https://example.org"}]},
            "Page\nURL: https://example.org\nExtrait: ",
        ),
        (
            {
                "results": [
                    {"title": "Page", "url": "https://example.org", "content": None}
                ]
            },
            "Page\nURL: https://example.org\nExtrait: ",
        ),
    ],
)
async def test_web_search_handles_empty_and_partial_results(
    monkeypatch, payload, expected
):
    _mock_client(monkeypatch, lambda request: httpx.Response(200, json=payload))

    assert await WebSearch("http://localhost:8888").execute(query="test") == expected


async def test_web_search_reports_unavailable_service(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    _mock_client(monkeypatch, handler)

    assert await WebSearch("http://localhost:8888").execute(query="test") == (
        "Error: search service is unavailable."
    )


async def test_web_search_reports_http_error(monkeypatch):
    _mock_client(monkeypatch, lambda request: httpx.Response(503))

    assert await WebSearch("http://localhost:8888").execute(query="test") == (
        "Error: search service returned HTTP 503."
    )


async def test_web_search_reports_invalid_json(monkeypatch):
    _mock_client(monkeypatch, lambda request: httpx.Response(200, text="not JSON"))

    assert await WebSearch("http://localhost:8888").execute(query="test") == (
        "Error: search service returned invalid JSON."
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"results": None},
        {"results": {}},
        {"results": [None]},
        {"results": [{"title": 3, "url": "https://example.org"}]},
    ],
)
async def test_web_search_reports_invalid_results(monkeypatch, payload):
    _mock_client(monkeypatch, lambda request: httpx.Response(200, json=payload))

    assert await WebSearch("http://localhost:8888").execute(query="test") == (
        "Error: search service returned invalid results."
    )

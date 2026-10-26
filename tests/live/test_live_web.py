"""Recent facts: the model must search, then answer from the results it got.

The search results are a fake SearXNG holding a fact no model can know, so a
right answer proves it was read from the tool, not recalled from training.
"""

import os

import pytest

pytestmark = pytest.mark.live

NOBEL = {
    "title": "Prix Nobel de physique 2026 : Ada Sentinelle récompensée",
    "url": "https://www.nobelprize.org/prizes/physics/2026/summary/",
    "content": (
        "Le prix Nobel de physique 2026 a été attribué à Ada Sentinelle pour ses "
        "travaux sur les qubits topologiques."
    ),
}


async def test_recent_fact_is_searched_then_answered_from_the_results(
    live_session, say, searxng
):
    searxng.results = [NOBEL]
    context = await live_session()

    exchange = await say(context, "Qui a reçu le prix Nobel de physique 2026 ?")
    print(exchange.transcript())

    assert [c.tool_name for c in exchange.tool_calls] == ["web_search"]
    assert "nobel" in exchange.tool_calls[0].arguments["query"].casefold()
    assert "Sentinelle" in exchange.text


async def test_answer_from_search_cites_its_source(live_session, say, searxng):
    searxng.results = [NOBEL]
    context = await live_session()

    exchange = await say(
        context, "Cherche qui a reçu le prix Nobel de physique 2026 et donne la source."
    )
    print(exchange.transcript())

    assert "nobelprize.org" in exchange.text


async def test_empty_search_is_admitted_not_invented(live_session, say, searxng):
    searxng.results = []
    context = await live_session()

    exchange = await say(context, "Qui a reçu le prix Nobel de physique 2026 ?")
    print(exchange.transcript())

    assert "web_search" in [c.tool_name for c in exchange.tool_calls]
    assert "Sentinelle" not in exchange.text


async def test_unreachable_search_is_explained_to_the_user(
    live_session, say, route_search
):
    import httpx

    def refuse(request):
        raise httpx.ConnectError("connection refused")

    route_search(refuse)
    context = await live_session()

    exchange = await say(context, "Quelle est la météo actuelle à Paris ?")
    print(exchange.transcript())

    assert "web_search" in [c.tool_name for c in exchange.tool_calls]
    assert exchange.text.strip()
    assert "°" not in exchange.text  # no invented temperature


@pytest.mark.skipif(
    not os.environ.get("SENSAI_LIVE_SEARXNG"),
    reason="set SENSAI_LIVE_SEARXNG=1 with `docker compose up searxng` running",
)
async def test_real_search_answer_links_a_returned_page(live_session, say):
    context = await live_session()

    exchange = await say(context, "Quelle est la dernière version stable de Python ?")
    print(exchange.transcript())

    results = "\n".join(
        m.content for m in context.engine.conversation.messages if m.role == "tool"
    )
    urls = [
        line.removeprefix("URL: ")
        for line in results.splitlines()
        if line.startswith("URL: ")
    ]
    assert urls, "the search returned no page"
    assert any(url in exchange.text for url in urls)

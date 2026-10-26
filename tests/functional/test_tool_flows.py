"""Tool calls end to end: model asks, user confirms or not, result goes back."""

from sensai.domain.events import MaxStepsEvent, StepEvent, ToolCallEvent


def call(name: str, **arguments) -> ToolCallEvent:
    return ToolCallEvent(tool_name=name, arguments=arguments)


def tool_results(context) -> list[str]:
    return [m.content for m in context.engine.conversation.messages if m.role == "tool"]


async def test_listing_then_reading_feeds_the_file_back_to_the_model(
    workspace, open_session, say
):
    (workspace / "notes.md").write_text("Collecte décalée au jeudi.", encoding="utf-8")
    context = await open_session(
        call("list_dir", path="."),
        call("read_file", path="notes.md"),
        "La collecte est décalée au jeudi.",
    )

    exchange = await say(context, "Que dit le fichier notes.md ?")

    assert [e.tool_name for e in exchange.of(ToolCallEvent)] == [
        "list_dir",
        "read_file",
    ]
    assert not exchange.confirmations  # reading needs no confirmation
    assert "notes.md" in tool_results(context)[0]
    last_prompt = context.engine.provider.calls[-1].messages
    assert last_prompt[-1].role == "tool"
    assert last_prompt[-1].content == "Collecte décalée au jeudi."
    assert exchange.text.endswith("La collecte est décalée au jeudi.")


async def test_reading_outside_the_allowed_root_is_refused(
    workspace, open_session, say
):
    context = await open_session(
        call("read_file", path="../../etc/passwd"),
        "Je ne peux pas lire ce fichier.",
    )

    await say(context, "Lis /etc/passwd")

    assert tool_results(context)[0].startswith("Error:")
    assert "root:" not in tool_results(context)[0]


async def test_approved_write_shows_a_preview_then_creates_the_file(
    workspace, open_session, say
):
    report = "# Incident\nBac renversé rue des Lilas.\n"
    context = await open_session(
        call("write_file", path="rapports/test.md", content=report),
        "Rapport écrit dans rapports/test.md.",
    )

    exchange = await say(context, "Écris un rapport d'incident dans rapports/test.md")

    [asked] = exchange.confirmations
    assert asked.name == "write_file"
    assert "+Bac renversé rue des Lilas." in asked.preview
    assert (workspace / "rapports" / "test.md").read_text(encoding="utf-8") == report
    assert exchange.text.endswith("Rapport écrit dans rapports/test.md.")


async def test_declined_write_leaves_the_disk_untouched_and_ends_the_turn(
    workspace, open_session, say
):
    context = await open_session(
        call("write_file", path="rapports/test.md", content="x"),
        "never played",
    )

    exchange = await say(context, "Écris un rapport", approve=False)

    assert not (workspace / "rapports").exists()
    assert exchange.text == "I didn't run the requested tool: write_file."
    assert len(context.engine.provider.calls) == 1  # no call after a refusal


async def test_web_search_results_reach_the_model_with_their_source(
    open_session, say, searxng
):
    context = await open_session(
        call("web_search", query="Python 3.15 release"),
        "Python 3.15 est sorti (source : https://www.python.org/downloads/release/python-3150/).",
    )

    exchange = await say(context, "Quelle est la dernière version de Python ?")

    assert exchange.confirmations[0].name == "web_search"
    assert searxng.queries == ["Python 3.15 release"]
    [result] = tool_results(context)
    assert "Python 3.15 released" in result
    assert "URL: https://www.python.org/downloads/release/python-3150/" in result
    assert "https://www.python.org" in exchange.text


async def test_search_outage_is_reported_to_the_model_not_raised(
    open_session, say, route_search
):
    import httpx

    def unreachable(request):
        raise httpx.ConnectError("connection refused")

    route_search(unreachable)
    context = await open_session(
        call("web_search", query="actualités"),
        "La recherche web est indisponible.",
    )

    exchange = await say(context, "Cherche les actualités")

    assert tool_results(context) == ["Error: search service is unavailable."]
    assert exchange.text.endswith("La recherche web est indisponible.")


async def test_remembered_fact_is_known_in_a_new_conversation(open_session, say):
    context = await open_session(
        call("remember_fact", entity="user", key="secteur", value="C"),
        "C'est noté : secteur C.",
        "Ton secteur est le C.",
    )

    await say(context, "Retiens que je travaille sur le secteur C")
    await say(context, "/new")
    await say(context, "Quel est mon secteur ?")

    prompt = context.engine.provider.calls[-1].messages
    system = "\n".join(m.content for m in prompt if m.role == "system")
    assert "- user.secteur: C" in system
    assert [m.role for m in prompt if m.role != "system"] == ["user"]  # fresh history
    assert context.structured_memory.get_fact("user", "secteur").value == "C"


async def test_forgetting_a_fact_asks_first_then_deletes_it(open_session, say):
    context = await open_session(
        call("forget_fact", entity="user", key="secteur"),
        "J'ai oublié ton secteur.",
    )
    context.structured_memory.store_fact("user", "secteur", "C")

    exchange = await say(context, "Oublie mon secteur")

    [asked] = exchange.confirmations
    assert "-user.secteur = C" in asked.preview
    assert context.structured_memory.get_fact("user", "secteur") is None


async def test_tool_unknown_to_the_registry_is_reported_back(open_session, say):
    context = await open_session(
        call("delete_everything"),
        "Je n'ai pas cet outil.",
    )

    exchange = await say(context, "Supprime tout")

    assert tool_results(context) == [
        "Error: Tool 'delete_everything' not found in registry."
    ]
    assert exchange.text.endswith("Je n'ai pas cet outil.")


async def test_tool_loop_is_capped_and_ends_with_a_tool_free_answer(open_session, say):
    loops = [call("list_dir", path=".") for _ in range(5)]
    context = await open_session(*loops, "Je m'arrête ici.")

    exchange = await say(context, "Explore tout")

    assert len(exchange.of(StepEvent)) == 5
    assert exchange.of(MaxStepsEvent)
    calls = context.engine.provider.calls
    assert len(calls) == 6
    assert calls[-1].tools is None
    assert exchange.text.endswith("Je m'arrête ici.")

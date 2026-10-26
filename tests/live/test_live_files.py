"""Local files: the answer must come from the file, writes must match the request."""

import pytest

pytestmark = pytest.mark.live


async def test_answer_quotes_the_file_it_read(workspace, live_session, say):
    (workspace / "NOTES.md").write_text(
        "Le code du portail du dépôt est 4729.", encoding="utf-8"
    )
    context = await live_session()

    exchange = await say(context, "Quel est le code du portail noté dans notes.md ?")
    print(exchange.transcript())

    assert "read_file" in [c.tool_name for c in exchange.tool_calls]
    assert "4729" in exchange.text


async def test_listing_is_counted_right(workspace, live_session, say):
    for name in ("a.md", "b.md", "c.md", "image.png"):
        (workspace / name).write_text("x", encoding="utf-8")
    context = await live_session()

    exchange = await say(context, "Combien de fichiers .md y a-t-il dans le dossier ?")
    print(exchange.transcript())

    assert "list_dir" in [c.tool_name for c in exchange.tool_calls]
    assert "3" in exchange.text or "trois" in exchange.text.casefold()


async def test_missing_file_is_reported_not_invented(workspace, live_session, say):
    (workspace / "securite-collecte.md").write_text("Port des gants.", encoding="utf-8")
    context = await live_session()

    exchange = await say(context, "Résume le document securite-vehicules.md.")
    print(exchange.transcript())

    words = exchange.text.casefold()
    missing = ("introuvable", "n'existe pas", "pas trouvé", "ne trouve pas", "aucun")
    assert any(w in words for w in missing), (
        "the model should say the file does not exist"
    )


async def test_approved_write_puts_the_requested_text_in_the_file(
    workspace, live_session, say
):
    context = await live_session()

    exchange = await say(
        context,
        "Écris exactement « Bac renversé rue des Lilas » dans rapports/incident.md.",
    )
    print(exchange.transcript())

    assert [c.name for c in exchange.confirmations] == ["write_file"]
    written = (workspace / "rapports" / "incident.md").read_text(encoding="utf-8")
    assert "Bac renversé rue des Lilas" in written


async def test_declined_write_creates_nothing(workspace, live_session, say):
    context = await live_session()

    exchange = await say(
        context, "Écris « test » dans rapports/test.md.", approve=False
    )
    print(exchange.transcript())

    assert exchange.confirmations
    assert not (workspace / "rapports").exists()

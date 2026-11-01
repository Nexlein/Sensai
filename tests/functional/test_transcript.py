"""The transcript live tests print: what the model thought, called, got and said."""

from sensai.domain.events import ThoughtEvent, ToolCallEvent


async def test_transcript_shows_thoughts_tool_results_and_guardrails(
    workspace, open_session, say
):
    (workspace / "notes.md").write_text(
        "Port des gants.\nGilet jaune.", encoding="utf-8"
    )
    context = await open_session(
        [
            ThoughtEvent(content="Je lis\nle fichier.", source="native"),
            ToolCallEvent(tool_name="read_file", arguments={"path": "notes.md"}),
        ],
        "Écrire à jean.martin@example.com.",
    )

    exchange = await say(context, "Que dit notes.md ?")

    lines = exchange.transcript().splitlines()
    assert lines[0] == "user: Que dit notes.md ?"
    # Lines follow the event order; a short thought is released after the call.
    assert "  thought: Je lis le fichier." in lines
    tool = lines.index("  tool read_file({'path': 'notes.md'})")
    assert lines[tool + 1] == "    -> Port des gants. Gilet jaune."
    assert any(line.startswith("  guardrail output redact: ") for line in lines)
    assert lines[-1] == "sensai: Écrire à [EMAIL]."


async def test_transcript_shows_the_step_cap_and_an_empty_answer(open_session, say):
    context = await open_session(
        ToolCallEvent(tool_name="list_dir", arguments={"path": "."}),
        [],
        config="[reasoning]\nmax_steps = 1\n",
    )

    exchange = await say(context, "Explore tout")

    lines = exchange.transcript().splitlines()
    assert "  max steps reached (1)" in lines
    assert lines[-1] == "sensai: (no answer)"

from collections.abc import AsyncIterator

import httpx
import pytest
from rich.console import Console

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import (
    AssistantStartEvent,
    BudgetEvent,
    Event,
    GuardrailEvent,
    TextChunkEvent,
    ToolCallEvent,
)
from sensai.domain.models import Conversation
from sensai.interfaces.cli.renderer import error_text, render_history, render_stream


def test_render_history_prints_prior_messages(capsys):
    console = Console()
    conversation = Conversation()
    conversation.add_message(role="user", content="hello")
    conversation.add_message(role="assistant", content="hi there")

    render_history(console, conversation)

    out = capsys.readouterr().out
    assert "you:" in out
    assert "hello" in out
    assert "sensai:" in out
    assert "hi there" in out


def test_render_history_skips_empty_conversation(capsys):
    console = Console()
    render_history(console, Conversation())

    assert capsys.readouterr().out == ""


async def _events(*items: Event) -> AsyncIterator[Event]:
    for item in items:
        yield item


async def test_render_stream_prints_text_chunks(capsys):
    console = Console()
    await render_stream(
        console, _events(TextChunkEvent(content="hel"), TextChunkEvent(content="lo"))
    )

    out = capsys.readouterr().out
    assert "sensai:" in out
    assert "hello" in out


async def test_render_stream_shows_speaker_before_first_chunk():
    from io import StringIO

    output = StringIO()
    console = Console(file=output, force_terminal=False)

    async def events():
        yield AssistantStartEvent()
        assert output.getvalue() == "sensai: "
        yield TextChunkEvent(content="Bonjour")

    await render_stream(console, events())
    assert output.getvalue() == "sensai: Bonjour\n"


async def test_render_stream_ignores_non_text_events(capsys):
    console = Console()
    await render_stream(
        console,
        _events(
            ToolCallEvent(tool_name="fs", arguments={}), TextChunkEvent(content="hi")
        ),
    )

    assert "hi" in capsys.readouterr().out


async def test_render_stream_shows_notice_for_blocked_input_without_empty_reply(
    capsys,
):
    console = Console()
    await render_stream(
        console,
        _events(
            GuardrailEvent(
                stage="input", action="block", reason="injection: ignore_instructions"
            )
        ),
    )

    out = capsys.readouterr().out
    assert "Message blocked" in out
    assert "injection: ignore_instructions" in out
    assert "sensai:" not in out


async def test_render_stream_shows_output_notice_after_the_masked_reply(capsys):
    console = Console()
    await render_stream(
        console,
        _events(
            TextChunkEvent(content="Write to [EMAIL]"),
            GuardrailEvent(stage="output", action="redact", reason="pii: email"),
        ),
    )

    out = capsys.readouterr().out
    assert "sensai: Write to [EMAIL]" in out
    assert "Personal data in the reply was masked" in out


async def test_render_stream_shows_usage_footer(capsys):
    console = Console()
    await render_stream(
        console,
        _events(
            BudgetEvent(used=100, max_tokens=1000),
            TextChunkEvent(content="hi"),
            BudgetEvent(used=101, max_tokens=1000),
        ),
    )

    out = capsys.readouterr().out
    assert "hi" in out
    assert "101 / 1.0k tokens (10%)" in out


async def test_render_stream_footer_shows_before_first_chunk(capsys):
    console = Console()
    await render_stream(console, _events(BudgetEvent(used=100, max_tokens=1000)))

    assert "100 / 1.0k tokens (10%)" in capsys.readouterr().out


async def test_render_stream_without_budget_prints_no_footer(capsys):
    console = Console()
    await render_stream(console, _events(TextChunkEvent(content="hi")))

    assert "tokens" not in capsys.readouterr().out


def test_error_text_reports_empty_input():
    assert "Empty input" in error_text(EmptyInputError("user_text must not be empty"))


def test_error_text_reports_connection_failure():
    exc = ProviderError("provider request failed")
    exc.__cause__ = httpx.ConnectError("connection refused")
    assert "Connection failed" in error_text(exc)


def test_error_text_reports_unavailable_model():
    exc = ProviderError("provider request failed")
    exc.__cause__ = RuntimeError("HTTP Provider Error [404]: model not found")
    assert "Model unavailable" in error_text(exc)


def test_error_text_handles_unknown_exception():
    text = error_text(ValueError("boom"))
    assert "Unexpected error" in text
    assert "boom" in text


@pytest.mark.parametrize(
    "answer, approved",
    [
        ("y", True),
        ("yes", True),
        ("1", True),
        ("no", False),
        ("2", False),
        ("maybe", False),
        ("", True),
        (EOFError(), False),
        (KeyboardInterrupt(), False),
    ],
)
async def test_confirmation_keeps_streamed_text_and_resumes_reply(
    monkeypatch, answer, approved
):
    from io import StringIO

    from sensai.domain.models import ToolCall
    from sensai.interfaces.cli.renderer import CliRenderer

    output = StringIO()
    console = Console(file=output, force_terminal=False)
    renderer = CliRenderer(console)

    def read_answer():
        assert output.getvalue().startswith("sensai: Avant la recherche.\n")
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr("builtins.input", read_answer)

    async def events():
        yield TextChunkEvent(content="Avant la recherche.")
        assert (
            await renderer.confirm_tool(
                ToolCall(name="web_search", arguments={"query": "[test]"})
            )
            is approved
        )
        yield TextChunkEvent(content="Après la décision.")

    await renderer.render(events())
    rendered = output.getvalue()
    assert "  Allow web_search?\n    query  [test]\n  [Yes/No] " in rendered
    decision = "✓ allowed web_search" if approved else "✗ declined web_search"
    assert f"  {decision}\n" in rendered
    assert rendered.count("Avant la recherche.") == 1
    assert rendered.count("Après la décision.") == 1


async def test_interactive_confirmation_uses_selector(monkeypatch):
    from io import StringIO

    from sensai.domain.models import ToolCall
    from sensai.interfaces.cli import renderer as renderer_module
    from sensai.interfaces.cli.renderer import CliRenderer
    from sensai.interfaces.prompts import tool_confirmation

    asked = []

    async def fake_select(question):
        asked.append(question)
        return True

    monkeypatch.setattr(renderer_module, "select", fake_select)
    monkeypatch.setattr(CliRenderer, "_interactive", lambda self: True)
    output = StringIO()
    renderer = CliRenderer(Console(file=output, force_terminal=False))
    tc = ToolCall(name="web_search", arguments={"query": "Sensai"})

    assert await renderer.confirm_tool(tc) is True
    assert asked == [tool_confirmation(tc)]
    assert output.getvalue() == "  ✓ allowed web_search\n"


async def test_confirmation_prints_diff_before_asking(monkeypatch):
    from io import StringIO

    from sensai.domain.models import ToolCall
    from sensai.interfaces.cli import renderer as renderer_module
    from sensai.interfaces.cli.renderer import CliRenderer

    output = StringIO()

    async def fake_select(question):
        assert "+ hello" in output.getvalue()
        return False

    monkeypatch.setattr(renderer_module, "select", fake_select)
    monkeypatch.setattr(CliRenderer, "_interactive", lambda self: True)
    renderer = CliRenderer(Console(file=output, force_terminal=False))
    tc = ToolCall(
        name="write_file",
        arguments={"path": "a.txt", "content": "hello"},
        preview="@@ -0,0 +1 @@\n+hello",
    )

    assert await renderer.confirm_tool(tc) is False
    assert output.getvalue().startswith("● write_file(a.txt)\n  ⎿  +1 -0\n")

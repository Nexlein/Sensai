import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from sensai.core.commands import CommandResult, RenderFn
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import (
    BudgetEvent,
    Event,
    GuardrailEvent,
    MaxStepsEvent,
    StepEvent,
    TextChunkEvent,
    ThoughtEvent,
    ToolCallEvent,
    UsageEvent,
)
from sensai.interfaces.tui.renderer import (
    AssistantMessage,
    ChatApp,
    ErrorMessage,
    GuardrailNotice,
    RoleLabel,
    StepLabel,
    ThoughtMessage,
    UsageLabel,
    UserMessage,
    error_text,
)


async def _events(*items: Event) -> AsyncIterator[Event]:
    for item in items:
        yield item


async def _raising(exc: Exception) -> AsyncIterator[Event]:
    raise exc
    yield  # pragma: no cover


def _process_events(*items: Event):
    async def process(text: str, render: RenderFn, confirm_tool) -> CommandResult:
        await render(_events(*items))
        return CommandResult()

    return process


@pytest.mark.asyncio
async def test_submitting_input_mounts_user_message_and_streamed_reply():
    app = ChatApp(
        _process_events(TextChunkEvent(content="hel"), TextChunkEvent(content="lo"))
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        for char in "hi":
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause()

        user_messages = app.query(UserMessage)
        assert len(user_messages) == 1
        assert "hi" in user_messages.first().source

        assistant_messages = app.query(AssistantMessage)
        assert len(assistant_messages) == 1
        assert assistant_messages.first().source == "hello"


@pytest.mark.asyncio
async def test_speaker_is_visible_before_first_model_chunk():
    waiting = asyncio.Event()
    release = asyncio.Event()

    async def events() -> AsyncIterator[Event]:
        waiting.set()
        await release.wait()
        yield TextChunkEvent(content="Bonjour")

    async def process(text: str, render: RenderFn, confirm_tool) -> CommandResult:
        await render(events())
        return CommandResult()

    app = ChatApp(process)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await asyncio.wait_for(waiting.wait(), timeout=2)
        labels = app.query(RoleLabel)
        assert [
            str(label.content) for label in labels if "assistant" in label.classes
        ] == ["sensai"]
        assert len(app.query(AssistantMessage)) == 0
        release.set()
        await pilot.pause()
        assert app.query(AssistantMessage).first().source == "Bonjour"


@pytest.mark.asyncio
async def test_submitting_input_ignores_non_text_events():
    app = ChatApp(
        _process_events(
            ToolCallEvent(tool_name="fs", arguments={}),
            TextChunkEvent(content="hi"),
        )
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        assert app.query(AssistantMessage).first().source == "hi"


@pytest.mark.asyncio
async def test_blocked_input_mounts_notice_and_no_empty_reply():
    app = ChatApp(
        _process_events(
            GuardrailEvent(
                stage="input", action="block", reason="injection: ignore_instructions"
            )
        )
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        notices = app.query(GuardrailNotice)
        assert len(notices) == 1
        assert "Message blocked" in str(notices.first().content)
        assert "injection: ignore_instructions" in str(notices.first().content)
        assert len(app.query(AssistantMessage)) == 0
        assert len(app.query("RoleLabel.assistant")) == 0


@pytest.mark.asyncio
async def test_masked_reply_shows_text_then_notice():
    app = ChatApp(
        _process_events(
            TextChunkEvent(content="Write to [EMAIL]"),
            GuardrailEvent(stage="output", action="redact", reason="pii: email"),
        )
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        assert app.query(AssistantMessage).first().source == "Write to [EMAIL]"
        notices = app.query(GuardrailNotice)
        assert len(notices) == 1
        assert "masked" in str(notices.first().content)


@pytest.mark.asyncio
async def test_budget_events_update_a_single_usage_label():
    app = ChatApp(
        _process_events(
            BudgetEvent(used=100, max_tokens=1000),
            TextChunkEvent(content="hi"),
            BudgetEvent(used=101, max_tokens=1000),
        )
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        labels = app.query(UsageLabel)
        assert len(labels) == 1
        assert "101 / 1.0k tokens (10%)" in str(labels.first().content)
        assert app.query(AssistantMessage).first().source == "hi"


@pytest.mark.asyncio
async def test_real_counters_join_the_usage_label():
    app = ChatApp(
        _process_events(
            BudgetEvent(used=100, max_tokens=1000),
            TextChunkEvent(content="hi"),
            UsageEvent(prompt_tokens=90, reply_tokens=12),
        )
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        (label,) = app.query(UsageLabel)
        text = str(label.content)
        assert "100 / 1.0k tokens (10%)" in text
        assert "prompt 90 tok · reply 12 tok" in text


@pytest.mark.asyncio
async def test_no_usage_label_without_budget_events():
    app = ChatApp(_process_events(TextChunkEvent(content="hi")))

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        assert len(app.query(UsageLabel)) == 0


@pytest.mark.asyncio
async def test_provider_error_mounts_error_message():
    exc = ProviderError("provider request failed")
    exc.__cause__ = httpx.ConnectError("connection refused")

    async def process(text: str, render: RenderFn, confirm_tool) -> CommandResult:
        await render(_raising(exc))
        return CommandResult()

    app = ChatApp(process)
    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        error_messages = app.query(ErrorMessage)
        assert len(error_messages) == 1
        assert "Connection failed" in str(error_messages.first().content)


@pytest.mark.asyncio
async def test_command_result_is_shown_without_empty_streamed_reply():
    async def process(text: str, render: RenderFn, confirm_tool) -> CommandResult:
        assert text == "/clear"
        return CommandResult(message="Conversation cleared.")

    app = ChatApp(process)
    async with app.run_test() as pilot:
        await pilot.click("Input")
        for char in "/clear":
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause()

        replies = app.query(AssistantMessage)
        assert len(replies) == 1
        assert replies.first().source == "Conversation cleared."


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
    "keys, approved",
    [
        (["enter"], True),
        (["1"], True),
        (["2"], False),
        (["down", "enter"], False),
        (["down", "down", "enter"], True),
        (["up", "enter"], False),
        (["escape"], False),
    ],
)
async def test_tool_confirmation_prompt_replaces_input_and_chat_resumes(keys, approved):
    from textual.widgets import Input

    from sensai.domain.models import ToolCall
    from sensai.interfaces.tui.question import QuestionPrompt
    from sensai.interfaces.tui.renderer import ToolDecisionNotice

    decisions = []

    async def process(text, render, confirm_tool):
        decisions.append(
            await confirm_tool(
                ToolCall(name="web_search", arguments={"query": "Sensai"})
            )
        )
        await render(_events(TextChunkEvent(content="Terminé")))
        return CommandResult()

    app = ChatApp(process)
    async with app.run_test() as pilot:
        input_widget = app.query_one(Input)
        await pilot.press("enter")
        await pilot.pause()
        prompt = app.query_one(QuestionPrompt)
        assert app.focused is prompt
        assert not input_widget.display
        for key in keys:
            await pilot.press(key)
        await pilot.pause()
        assert decisions == [approved]
        assert not app.query(QuestionPrompt)
        assert input_widget.display
        notice = app.query_one(ToolDecisionNotice)
        assert notice.has_class("approved" if approved else "declined")
        expected = "✓ allowed web_search" if approved else "✗ declined web_search"
        assert str(notice.render()) == expected
        assert app.query(AssistantMessage).first().source == "Terminé"
        assert not input_widget.disabled


async def test_question_prompt_shows_title_details_and_options():
    from sensai.domain.models import ToolCall
    from sensai.interfaces.prompts import tool_confirmation
    from sensai.interfaces.tui.question import QuestionPrompt

    async def process(text, render, confirm_tool):
        await confirm_tool(
            ToolCall(name="web_search", arguments={"query": "café", "limit": 3})
        )
        return CommandResult()

    app = ChatApp(process)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        prompt = app.query_one(QuestionPrompt)
        assert prompt.question == tool_confirmation(
            ToolCall(name="web_search", arguments={"query": "café", "limit": 3})
        )
        lines = prompt.render().plain.splitlines()
        assert lines[:3] == ["Allow web_search?", "  query  café", "  limit  3"]
        assert "❯ 1. Yes" in lines
        assert "  2. No" in lines
        await pilot.press("down")
        lines = prompt.render().plain.splitlines()
        assert "  1. Yes" in lines
        assert "❯ 2. No" in lines
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_thinking_time_shows_while_waiting_and_goes_when_the_reply_starts(
    monkeypatch,
):
    from sensai.interfaces import thinking
    from sensai.interfaces.tui.renderer import ThinkingLabel

    monkeypatch.setattr(thinking, "GRACE_SECONDS", 0.05)
    monkeypatch.setattr(thinking, "TICK_SECONDS", 0.05)
    release = asyncio.Event()

    async def events() -> AsyncIterator[Event]:
        await release.wait()
        yield TextChunkEvent(content="Bonjour")

    async def process(text: str, render: RenderFn, confirm_tool) -> CommandResult:
        await render(events())
        return CommandResult()

    app = ChatApp(process)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await asyncio.sleep(0.3)
        await pilot.pause()
        labels = app.query(ThinkingLabel)
        assert len(labels) == 1
        assert "thinking…" in str(labels.first().render())
        assert "Esc to stop" in str(labels.first().render())

        release.set()
        await pilot.pause()
        await pilot.pause()
        assert len(app.query(ThinkingLabel)) == 0
        assert app.query(AssistantMessage).first().source == "Bonjour"


@pytest.mark.asyncio
async def test_escape_stops_the_turn_and_gives_the_prompt_back():
    from textual.widgets import Input

    from sensai.interfaces.tui.renderer import StoppedNotice

    started = asyncio.Event()

    async def events() -> AsyncIterator[Event]:
        started.set()
        await asyncio.sleep(60)
        yield TextChunkEvent(content="never")

    async def process(text: str, render: RenderFn, confirm_tool) -> CommandResult:
        await render(events())
        return CommandResult()

    app = ChatApp(process)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await asyncio.wait_for(started.wait(), timeout=2)
        assert app.query_one(Input).disabled

        await pilot.press("escape")
        await pilot.pause()
        await pilot.pause()

        assert len(app.query(StoppedNotice)) == 1
        assert not app.query_one(Input).disabled
        assert len(app.query(AssistantMessage)) == 0
        assert len(app.query(ErrorMessage)) == 0


@pytest.mark.asyncio
async def test_escape_with_no_turn_running_does_nothing():
    app = ChatApp(_process_events())

    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()

        assert app.is_running


@pytest.mark.asyncio
async def test_thoughts_and_steps_are_mounted_before_the_answer():
    app = ChatApp(
        _process_events(
            StepEvent(index=1, max_steps=5),
            ThoughtEvent(content="I should read the file"),
            StepEvent(index=2, max_steps=5),
            TextChunkEvent(content="done"),
        ),
        show_thoughts=True,
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        assert [str(w.render()) for w in app.query(StepLabel)] == [
            "step 1/5",
            "step 2/5",
        ]
        assert str(app.query(ThoughtMessage).first().render()) == (
            "I should read the file"
        )
        assert app.query(AssistantMessage).first().source == "done"


@pytest.mark.asyncio
async def test_thought_only_turn_keeps_the_speaker_label():
    app = ChatApp(_process_events(ThoughtEvent(content="thinking")), show_thoughts=True)

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        assert len(app.query(ThoughtMessage)) == 1
        assert len(app.query(RoleLabel)) == 2


@pytest.mark.asyncio
async def test_step_limit_mounts_a_notice():
    app = ChatApp(_process_events(MaxStepsEvent(max_steps=5)))

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        assert "Step limit (5) reached" in str(
            app.query(GuardrailNotice).first().render()
        )


@pytest.mark.asyncio
async def test_thought_chunks_merge_into_one_message():
    app = ChatApp(
        _process_events(
            ThoughtEvent(content="I should ", source="native"),
            ThoughtEvent(content="read it", source="native"),
            TextChunkEvent(content="done"),
        ),
        show_thoughts=True,
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        messages = list(app.query(ThoughtMessage))
        assert [str(m.render()) for m in messages] == ["I should read it"]


@pytest.mark.asyncio
async def test_thoughts_and_steps_hidden_by_default():
    app = ChatApp(
        _process_events(
            StepEvent(index=1, max_steps=5),
            ThoughtEvent(content="secret"),
            TextChunkEvent(content="done"),
        )
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        assert len(app.query(ThoughtMessage)) == 0
        assert len(app.query(StepLabel)) == 0
        assert app.query(AssistantMessage).first().source == "done"

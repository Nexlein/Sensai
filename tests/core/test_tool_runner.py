"""Tool runner: confirmation, execution, filtered results."""

import pytest

from sensai.core.tool_runner import (
    TOOL_CONFIRMATION_FAILED,
    TOOL_DECLINED,
    TOOL_RESULT_WITHHELD,
    ToolRunner,
)
from sensai.domain.events import GuardrailEvent
from sensai.domain.models import Conversation, ToolCall
from sensai.eval.guardrails import RegexGuardrail
from sensai.tools.registry import ToolRegistry


class FakeTool:
    name = "fake"
    description = "fake"
    parameters_schema = {}  # noqa: RUF012

    def __init__(self, requires_confirmation=False, preview=None, fail=False):
        self.requires_confirmation = requires_confirmation
        self.ran = 0
        self.fail = fail
        if preview is not None:
            self.preview = preview

    async def execute(self, **kwargs):
        self.ran += 1
        if self.fail:
            raise ValueError("boom")
        return "done"


def _runner(tool=None, guardrail=None):
    registry = ToolRegistry()
    if tool is not None:
        registry.register(tool)
    conversation = Conversation()
    return ToolRunner(registry, guardrail, conversation), conversation


def _call(**arguments):
    return ToolCall(name="fake", arguments=arguments)


@pytest.mark.asyncio
async def test_run_reports_an_unknown_tool():
    runner, _ = _runner()

    outcome = await runner.run(_call(), None)

    assert "not found" in outcome.result
    assert not outcome.declined


@pytest.mark.asyncio
async def test_run_executes_a_tool_without_confirmation():
    tool = FakeTool()
    runner, _ = _runner(tool)

    outcome = await runner.run(_call(), None)

    assert (outcome.result, outcome.declined, tool.ran) == ("done", False, 1)


@pytest.mark.asyncio
async def test_run_turns_a_tool_error_into_text():
    runner, _ = _runner(FakeTool(fail=True))

    outcome = await runner.run(_call(), None)

    assert outcome.result == "boom"
    assert not outcome.declined


@pytest.mark.asyncio
async def test_run_declines_without_a_confirm_callback():
    tool = FakeTool(requires_confirmation=True)
    runner, _ = _runner(tool)

    outcome = await runner.run(_call(), None)

    assert (outcome.result, outcome.declined, tool.ran) == (TOOL_DECLINED, True, 0)


@pytest.mark.asyncio
async def test_run_declines_when_the_user_says_no():
    tool = FakeTool(requires_confirmation=True)
    runner, _ = _runner(tool)

    async def no(_):
        return False

    outcome = await runner.run(_call(), no)

    assert (outcome.result, outcome.declined, tool.ran) == (TOOL_DECLINED, True, 0)


@pytest.mark.asyncio
async def test_run_never_authorizes_when_the_confirm_callback_fails():
    tool = FakeTool(requires_confirmation=True)
    runner, _ = _runner(tool)

    async def broken(_):
        raise RuntimeError("ui crashed")

    outcome = await runner.run(_call(), broken)

    assert outcome.result == TOOL_CONFIRMATION_FAILED
    assert outcome.declined
    assert tool.ran == 0


@pytest.mark.asyncio
async def test_run_hands_the_preview_to_the_confirmation():
    tool = FakeTool(requires_confirmation=True, preview=lambda **kw: "the diff")
    runner, _ = _runner(tool)
    seen = []

    async def yes(tc):
        seen.append(tc.preview)
        return True

    outcome = await runner.run(_call(), yes)

    assert (seen, outcome.result) == (["the diff"], "done")


@pytest.mark.asyncio
async def test_run_still_asks_when_the_preview_fails():
    def broken(**kwargs):
        raise ValueError("no preview")

    tool = FakeTool(requires_confirmation=True, preview=broken)
    runner, _ = _runner(tool)
    seen = []

    async def yes(tc):
        seen.append(tc.preview)
        return True

    await runner.run(_call(), yes)

    assert seen == [None]


@pytest.mark.asyncio
async def test_store_adds_the_result_as_a_tool_message():
    runner, conversation = _runner()

    events = [event async for event in runner.store("plain result")]

    assert events == []
    assert conversation.messages[-1].role == "tool"
    assert conversation.messages[-1].content == "plain result"


@pytest.mark.asyncio
async def test_store_redacts_personal_data_and_reports_it():
    runner, conversation = _runner(guardrail=RegexGuardrail())

    events = [event async for event in runner.store("mail me at jo@example.com")]

    assert "jo@example.com" not in conversation.messages[-1].content
    assert isinstance(events[0], GuardrailEvent)
    assert (events[0].stage, events[0].action) == ("tool", "redact")


@pytest.mark.asyncio
async def test_store_withholds_a_blocked_result():
    runner, conversation = _runner(guardrail=RegexGuardrail(pii_action="block"))

    events = [event async for event in runner.store("contact a@b.io")]

    assert isinstance(events[0], GuardrailEvent)
    assert events[0].action == "block"
    assert conversation.messages[-1].content == TOOL_RESULT_WITHHELD

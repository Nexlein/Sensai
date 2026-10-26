import pytest

from sensai.core.engine import ChatEngine
from sensai.core.prompt import STEP_LIMIT_NOTE
from sensai.domain.events import (
    GuardrailEvent,
    MaxStepsEvent,
    StepEvent,
    TextChunkEvent,
    ThoughtEvent,
    ToolCallEvent,
)
from sensai.domain.models import Conversation
from sensai.eval.guardrails import REFUSAL_TEXT, RegexGuardrail
from sensai.tools.registry import ToolRegistry


class DummyTool:
    requires_confirmation = False
    name = "dummy"
    description = "a dummy tool"
    parameters_schema = {}  # noqa: RUF012

    async def execute(self, **kwargs):
        return "tool result"


class ScriptedProvider:
    """Plays one scripted list of events per call, recording prompts and options."""

    def __init__(self, *scripts):
        self.scripts = scripts
        self.prompts = []
        self.tools_seen = []
        self.options_seen = []

    async def chat_stream(self, messages, tools=None, **options):
        self.prompts.append(list(messages))
        self.tools_seen.append(tools)
        self.options_seen.append(options)
        for event in self.scripts[len(self.prompts) - 1]:
            yield event


class LoopingProvider:
    """Calls the tool as long as tools are offered, answers once they are not."""

    def __init__(self):
        self.tools_seen = []
        self.prompts = []

    async def chat_stream(self, messages, tools=None, **options):
        self.tools_seen.append(tools)
        self.prompts.append(list(messages))
        if tools:
            yield TextChunkEvent(content="let me look")
            yield ToolCallEvent(tool_name="dummy", arguments={})
        else:
            yield TextChunkEvent(content="best effort")


def chunks(*parts):
    return [TextChunkEvent(content=part) for part in parts]


def call():
    return ToolCallEvent(tool_name="dummy", arguments={})


def build(provider, **kwargs):
    registry = ToolRegistry()
    registry.register(DummyTool())
    conversation = Conversation()
    engine = ChatEngine(provider, conversation, registry, **kwargs)
    return engine, conversation


async def run(engine, text="go"):
    return [event async for event in engine.send(text)]


def of_type(events, kind):
    return [event for event in events if isinstance(event, kind)]


def shown_text(events):
    return "".join(event.content for event in of_type(events, TextChunkEvent))


async def test_reasoning_off_drops_native_thoughts_and_keeps_old_behaviour():
    provider = ScriptedProvider(
        [ThoughtEvent(content="secret", source="native"), *chunks("looking"), call()],
        chunks("done"),
    )
    engine, conversation = build(provider)

    events = await run(engine)

    assert of_type(events, ThoughtEvent) == []
    assert of_type(events, StepEvent) == []
    assert shown_text(events) == "lookingdone"
    assistant = conversation.messages[1]
    assert assistant.content == "looking"
    assert assistant.thought is None
    assert provider.options_seen == [{}, {}]


async def test_native_thought_is_emitted_and_stored_on_the_final_answer():
    provider = ScriptedProvider(
        [
            ThoughtEvent(content="need ", source="native"),
            ThoughtEvent(content="the file", source="native"),
            *chunks("the answer"),
        ]
    )
    engine, conversation = build(provider, reasoning=True)

    events = await run(engine)

    thoughts = of_type(events, ThoughtEvent)
    assert [t.content for t in thoughts] == ["need ", "the file"]
    assert {t.source for t in thoughts} == {"native"}
    assert shown_text(events) == "the answer"
    assert conversation.messages[-1].content == "the answer"
    assert conversation.messages[-1].thought == "need the file"


async def test_text_before_a_tool_call_becomes_a_thought_not_an_answer():
    provider = ScriptedProvider(
        [*chunks("I should ", "read it"), call()], chunks("final")
    )
    engine, conversation = build(provider, reasoning=True)

    events = await run(engine)

    (thought,) = of_type(events, ThoughtEvent)
    assert (thought.content, thought.source) == ("I should read it", "text")
    assert shown_text(events) == "final"
    assistant = conversation.messages[1]
    assert assistant.content == ""
    assert assistant.thought == "I should read it"
    assert assistant.tool_calls is not None
    assert assistant.tool_calls[0].name == "dummy"
    assert conversation.messages[-1].thought is None


async def test_thought_is_emitted_before_its_tool_call():
    provider = ScriptedProvider([*chunks("thinking"), call()], chunks("ok"))
    engine, _ = build(provider, reasoning=True)

    events = await run(engine)

    order = [type(e) for e in events if isinstance(e, ThoughtEvent | ToolCallEvent)]
    assert order == [ThoughtEvent, ToolCallEvent]


async def test_native_and_text_thoughts_are_stored_together():
    provider = ScriptedProvider(
        [ThoughtEvent(content="deep", source="native"), *chunks("shallow"), call()],
        chunks("ok"),
    )
    engine, conversation = build(provider, reasoning=True)

    await run(engine)

    assert conversation.messages[1].thought == "deep\nshallow"


async def test_whitespace_before_a_tool_call_is_not_a_thought():
    provider = ScriptedProvider([*chunks(" \n"), call()], chunks("ok"))
    engine, conversation = build(provider, reasoning=True)

    events = await run(engine)

    assert of_type(events, ThoughtEvent) == []
    assert conversation.messages[1].content == ""
    assert conversation.messages[1].thought is None


async def test_reply_without_tool_calls_streams_as_the_answer():
    provider = ScriptedProvider([*chunks("just ", "an answer")])
    engine, conversation = build(provider, reasoning=True)

    events = await run(engine)

    assert of_type(events, ThoughtEvent) == []
    assert [e.content for e in of_type(events, TextChunkEvent)] == [
        "just ",
        "an answer",
    ]
    assert conversation.messages[-1].content == "just an answer"


async def test_without_tools_text_is_not_held_back():
    provider = ScriptedProvider(chunks("a", "b"))
    conversation = Conversation()
    engine = ChatEngine(provider, conversation, reasoning=True)

    events = await run(engine)

    assert shown_text(events) == "ab"
    assert of_type(events, ThoughtEvent) == []


async def test_a_step_event_opens_each_round():
    provider = ScriptedProvider([call()], [call()], chunks("done"))
    engine, _ = build(provider, reasoning=True, max_steps=5)

    events = await run(engine)

    steps = of_type(events, StepEvent)
    assert [(s.index, s.max_steps) for s in steps] == [(1, 5), (2, 5), (3, 5)]


async def test_thoughts_never_reach_the_next_prompt():
    provider = ScriptedProvider(
        [
            ThoughtEvent(content="NATIVE-PLAN", source="native"),
            *chunks("TEXT-PLAN"),
            call(),
        ],
        chunks("done"),
    )
    engine, _ = build(provider, reasoning=True)

    await run(engine)

    sent = [m.content for m in provider.prompts[1]]
    assert not any(
        "NATIVE-PLAN" in content or "TEXT-PLAN" in content for content in sent
    )


async def test_step_cap_forces_a_tool_free_final_answer():
    provider = LoopingProvider()
    engine, conversation = build(provider, reasoning=True, max_steps=2)

    events = await run(engine)

    assert len(provider.tools_seen) == 3
    assert provider.tools_seen[0] and provider.tools_seen[1]
    assert provider.tools_seen[2] is None
    assert [m.role for m in conversation.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]
    assert conversation.messages[-1].content == "best effort"
    assert shown_text(events) == "best effort"
    (limit,) = of_type(events, MaxStepsEvent)
    assert limit.max_steps == 2
    assert STEP_LIMIT_NOTE in [m.content for m in provider.prompts[2]]
    assert STEP_LIMIT_NOTE not in [m.content for m in provider.prompts[1]]


async def test_max_steps_event_comes_before_the_forced_answer():
    provider = LoopingProvider()
    engine, _ = build(provider, reasoning=True, max_steps=1)

    events = await run(engine)

    kinds = [type(e) for e in events if isinstance(e, MaxStepsEvent | TextChunkEvent)]
    assert kinds == [MaxStepsEvent, TextChunkEvent]


async def test_no_max_steps_event_when_the_model_answers_in_time():
    provider = ScriptedProvider([call()], chunks("done"))
    engine, _ = build(provider, reasoning=True, max_steps=2)

    events = await run(engine)

    assert of_type(events, MaxStepsEvent) == []
    assert len(provider.prompts) == 2


async def test_cap_without_reasoning_still_forces_a_silent_final_answer():
    provider = LoopingProvider()
    engine, conversation = build(provider, max_steps=2)

    events = await run(engine)

    assert of_type(events, MaxStepsEvent) == []
    assert len(provider.tools_seen) == 3
    assert provider.tools_seen[2] is None
    assert STEP_LIMIT_NOTE in [m.content for m in provider.prompts[2]]
    assert conversation.messages[-1].content == "best effort"
    assert shown_text(events).endswith("best effort")


def test_max_steps_must_be_positive():
    with pytest.raises(ValueError, match="max_steps"):
        ChatEngine(ScriptedProvider(), Conversation(), max_steps=0)


async def test_think_option_is_passed_to_the_provider_when_set():
    provider = ScriptedProvider(chunks("hi"))
    engine, _ = build(provider, reasoning=True, think="high")

    await run(engine)

    assert provider.options_seen == [{"think": "high"}]


async def test_think_option_is_omitted_when_unset_or_reasoning_is_off():
    provider = ScriptedProvider(chunks("hi"))
    engine, _ = build(provider, reasoning=True)
    await run(engine)

    other = ScriptedProvider(chunks("hi"))
    engine, _ = build(other, think=True)
    await run(engine)

    assert provider.options_seen == [{}]
    assert other.options_seen == [{}]


async def test_guardrail_redacts_a_native_thought():
    provider = ScriptedProvider(
        [
            ThoughtEvent(
                content="write to bob@example.com now please", source="native"
            ),
            *chunks("done"),
        ]
    )
    engine, conversation = build(provider, reasoning=True, guardrail=RegexGuardrail())

    events = await run(engine)

    shown = "".join(t.content for t in of_type(events, ThoughtEvent))
    assert "bob@example.com" not in shown
    assert "[EMAIL]" in shown
    assert conversation.messages[-1].thought is not None
    assert "bob@example.com" not in conversation.messages[-1].thought
    (notice,) = of_type(events, GuardrailEvent)
    assert (notice.stage, notice.action) == ("output", "redact")


async def test_guardrail_redacts_text_that_became_a_thought():
    provider = ScriptedProvider(
        [*chunks("I will mail bob@example.com about this today please"), call()],
        chunks("done"),
    )
    engine, conversation = build(provider, reasoning=True, guardrail=RegexGuardrail())

    events = await run(engine)

    (thought,) = of_type(events, ThoughtEvent)
    assert "bob@example.com" not in thought.content
    assert conversation.messages[1].thought is not None
    assert "bob@example.com" not in conversation.messages[1].thought


async def test_refused_reply_shows_the_refusal_and_runs_no_tool():
    provider = ScriptedProvider([*chunks("mail a@b.io"), call()])
    engine, conversation = build(
        provider, reasoning=True, guardrail=RegexGuardrail(pii_action="block")
    )

    events = await run(engine)

    assert REFUSAL_TEXT in shown_text(events)
    assert of_type(events, ThoughtEvent) == []
    assert len(provider.prompts) == 1
    assert [m.role for m in conversation.messages] == ["user", "assistant"]
    assert conversation.messages[-1].tool_calls is None


async def test_declined_tool_ends_the_turn_without_a_forced_answer():
    class SensitiveTool(DummyTool):
        requires_confirmation = True

    provider = ScriptedProvider([*chunks("plan"), call()])
    registry = ToolRegistry()
    registry.register(SensitiveTool())
    engine = ChatEngine(provider, Conversation(), registry, reasoning=True)

    async def decline(tc):
        return False

    events = [e async for e in engine.send("go", confirm_tool=decline)]

    assert of_type(events, MaxStepsEvent) == []
    assert len(provider.prompts) == 1
    assert "didn't run" in shown_text(events)


async def test_without_split_thoughts_text_streams_as_it_arrives():
    class Probe:
        def __init__(self):
            self.calls = 0
            self.tool_call_sent = False

        async def chat_stream(self, messages, tools=None, **options):
            self.calls += 1
            if self.calls == 1:
                yield TextChunkEvent(content="let me look")
                self.tool_call_sent = True
                yield call()
            else:
                yield TextChunkEvent(content="final")

    provider = Probe()
    engine, conversation = build(provider, reasoning=True, split_thoughts=False)

    sent_before_first_chunk = None
    async for event in engine.send("go"):
        if isinstance(event, TextChunkEvent) and sent_before_first_chunk is None:
            sent_before_first_chunk = provider.tool_call_sent

    assert sent_before_first_chunk is False
    assistant = conversation.messages[1]
    assert assistant.content == "let me look"
    assert assistant.thought is None


async def test_without_split_thoughts_no_text_becomes_a_thought():
    provider = ScriptedProvider([*chunks("I should ", "read it"), call()], chunks("x"))
    engine, _ = build(provider, reasoning=True, split_thoughts=False)

    events = await run(engine)

    assert of_type(events, ThoughtEvent) == []
    assert shown_text(events) == "I should read itx"

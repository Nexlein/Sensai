from collections.abc import AsyncGenerator
from typing import Any

import httpx

from sensai.core.budget import ContextBudget
from sensai.core.guard import guardrail_event
from sensai.core.turn import Round
from sensai.domain.errors import ProviderError
from sensai.domain.events import (
    BudgetEvent,
    Event,
    TextChunkEvent,
    ThoughtEvent,
    ToolCallEvent,
)
from sensai.domain.models import Message, ToolCall
from sensai.domain.protocols import Guardrail, LLMProvider


class RoundStreamer:
    """Settings for streaming provider calls; `open` starts one call."""

    def __init__(
        self,
        provider: LLMProvider,
        guardrail: Guardrail | None = None,
        budget: ContextBudget | None = None,
        reasoning: bool = False,
        split_thoughts: bool = True,
        think: bool | str | None = None,
    ) -> None:
        self.provider = provider
        self.guardrail = guardrail
        self.budget = budget
        self.reasoning = reasoning
        self.split_thoughts = split_thoughts
        self.think = think

    def open(
        self, prompt: list[Message], tools_schema: list[dict[str, Any]] | None
    ) -> "RoundStream":
        return RoundStream(self, prompt, tools_schema)


class RoundStream:
    """One provider call: `events` streams it and fills `reply` meanwhile.

    Text the output filter still holds back could be the start of a PII value, so
    it is settled only when the stream ends. During a round that may call tools,
    text and tool calls are held until the round is over: with tool calls the text
    was the model thinking aloud and becomes a thought, otherwise it is released
    as is. Provider failures surface as `ProviderError`.
    """

    def __init__(
        self,
        config: RoundStreamer,
        prompt: list[Message],
        tools_schema: list[dict[str, Any]] | None,
    ) -> None:
        guardrail = config.guardrail
        self.config = config
        self.prompt = prompt
        self.tools_schema = tools_schema
        self.reply = Round()
        self.tracker = config.budget.tracker(prompt) if config.budget else None
        self.stream = guardrail.new_output_stream() if guardrail else None
        self.thought_stream = (
            guardrail.new_output_stream() if guardrail and config.reasoning else None
        )
        self.hold = config.reasoning and config.split_thoughts and bool(tools_schema)
        self.held: list[str] = []
        self.held_tool_events: list[ToolCallEvent] = []

    async def events(self) -> AsyncGenerator[Event]:
        if self.tracker is not None:
            yield BudgetEvent(
                used=self.tracker.usage.used, max_tokens=self.tracker.max_tokens
            )
        async for event in self._provider_events():
            yield event
        for event in self._flush():
            yield event
        if self.hold:
            for event in self._release_held():
                yield event
        for event in self._guardrail_events():
            yield event

    def _options(self) -> dict[str, Any]:
        config = self.config
        if config.reasoning and config.think is not None:
            return {"think": config.think}
        return {}

    async def _provider_events(self) -> AsyncGenerator[Event]:
        try:
            async for event in self.config.provider.chat_stream(
                self.prompt, tools=self.tools_schema, **self._options()
            ):
                if isinstance(event, ThoughtEvent):
                    handled = self._on_thought(event)
                elif isinstance(event, ToolCallEvent):
                    handled = self._on_tool_call(event)
                elif isinstance(event, TextChunkEvent):
                    handled = self._on_text(event)
                else:
                    handled = [event]
                for out in handled:
                    yield out
        except ProviderError:
            raise
        except (RuntimeError, httpx.HTTPError) as exc:
            raise ProviderError("provider request failed") from exc

    def _on_thought(self, event: ThoughtEvent) -> list[Event]:
        if not self.config.reasoning:
            return []
        released = (
            self.thought_stream.feed(event.content)
            if self.thought_stream is not None
            else event.content
        )
        if not released:
            return []
        self.reply.native_thoughts.append(released)
        return [ThoughtEvent(content=released, source="native")]

    def _on_tool_call(self, event: ToolCallEvent) -> list[Event]:
        self.reply.tool_calls.append(
            ToolCall(name=event.tool_name, arguments=event.arguments)
        )
        if self.hold:
            self.held_tool_events.append(event)
            return []
        return [event]

    def _on_text(self, event: TextChunkEvent) -> list[Event]:
        content = event.content
        if self.stream is not None:
            content = self.stream.feed(content)
            if not content:
                return []
        self.reply.chunks.append(content)
        events: list[Event] = []
        if self.hold:
            self.held.append(content)
        else:
            events.append(TextChunkEvent(content=content))
        if self.tracker is not None:
            usage = self.tracker.add(content)
            events.append(BudgetEvent(used=usage.used, max_tokens=usage.max_tokens))
        return events

    def _flush(self) -> list[Event]:
        """Settle what the output filters were still holding back."""
        events: list[Event] = []
        if self.stream is not None:
            tail = self.stream.flush()
            if tail:
                self.reply.chunks.append(tail)
                if self.hold:
                    self.held.append(tail)
                else:
                    events.append(TextChunkEvent(content=tail))
            self.reply.refused = self.stream.refused
        if self.thought_stream is not None:
            tail = self.thought_stream.flush()
            if tail:
                self.reply.native_thoughts.append(tail)
                events.append(ThoughtEvent(content=tail, source="native"))
        return events

    def _release_held(self) -> list[Event]:
        """Settle the text held back during a round that may call tools."""
        reply = self.reply
        events: list[Event] = []
        if reply.tool_calls and not reply.refused:
            reply.text_thought = "".join(self.held)
            if reply.text_thought.strip():
                events.append(ThoughtEvent(content=reply.text_thought, source="text"))
        else:
            events.extend(TextChunkEvent(content=chunk) for chunk in self.held)
        events.extend(self.held_tool_events)
        return events

    def _guardrail_events(self) -> list[Event]:
        events: list[Event] = []
        guards = (
            (self.stream, self.reply.refused),
            (
                self.thought_stream,
                bool(self.thought_stream and self.thought_stream.refused),
            ),
        )
        for guard, refused in guards:
            if guard is not None and guard.findings:
                action = "block" if refused else "redact"
                events.append(guardrail_event("output", action, guard.findings))
        return events

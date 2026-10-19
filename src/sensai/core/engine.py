import asyncio
from collections.abc import AsyncGenerator

import httpx

from sensai.core.budget import ContextBudget
from sensai.core.guard import guardrail_event
from sensai.core.prompt import PromptComposer
from sensai.core.streaming import RoundStreamer
from sensai.core.tool_runner import ConfirmTool, ToolRunner
from sensai.core.turn import Round, Turn
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import (
    AssistantStartEvent,
    Event,
    GuardrailEvent,
    MaxStepsEvent,
    StepEvent,
    TextChunkEvent,
)
from sensai.domain.models import Conversation, Persona
from sensai.domain.protocols import (
    ContextRetriever,
    Guardrail,
    LLMProvider,
    ReplyRecorder,
    StructuredMemory,
    ToolRegistry,
)

MAX_TOOL_ROUNDS = 5


class ChatEngine:
    """Runs one user turn: guard, retrieve, then loop model call and tool calls."""

    def __init__(
        self,
        provider: LLMProvider,
        conversation: Conversation,
        registry: ToolRegistry | None = None,
        retriever: ContextRetriever | None = None,
        budget: ContextBudget | None = None,
        guardrail: Guardrail | None = None,
        recorder: ReplyRecorder | None = None,
        memory: StructuredMemory | None = None,
        memory_auto_inject: bool = True,
        reasoning: bool = False,
        split_thoughts: bool = True,
        max_steps: int = MAX_TOOL_ROUNDS,
        think: bool | str | None = None,
        persona: Persona | None = None,
        persona_enabled: bool = True,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self.provider = provider
        self.conversation = conversation
        self.registry = registry
        self.retriever = retriever
        self.budget = budget
        self.guardrail = guardrail
        self.recorder = recorder
        self.memory = memory
        self.memory_auto_inject = memory_auto_inject
        self.reasoning = reasoning
        self.split_thoughts = split_thoughts
        self.max_steps = max_steps
        self.think = think
        # Kept when disabled so `/persona on` can bring it back.
        self.persona = persona
        self.persona_enabled = persona_enabled

    @property
    def _streamer(self) -> RoundStreamer:
        return RoundStreamer(
            self.provider,
            guardrail=self.guardrail,
            budget=self.budget,
            reasoning=self.reasoning,
            split_thoughts=self.split_thoughts,
            think=self.think,
        )

    @property
    def _tools(self) -> ToolRunner:
        return ToolRunner(self.registry, self.guardrail, self.conversation)

    @property
    def _composer(self) -> PromptComposer:
        return PromptComposer(
            self.conversation,
            self.budget,
            self.memory,
            self.memory_auto_inject,
            persona=self.persona if self.persona_enabled else None,
        )

    async def send(
        self, user_text: str, confirm_tool: ConfirmTool | None = None
    ) -> AsyncGenerator[Event]:
        """Stream the events of one turn; a failed or cancelled turn leaves history untouched."""
        mark = len(self.conversation.messages)
        try:
            async for event in self._send(user_text, confirm_tool):
                yield event
        except (asyncio.CancelledError, ProviderError):
            del self.conversation.messages[mark:]
            raise

    async def _send(
        self, user_text: str, confirm_tool: ConfirmTool | None
    ) -> AsyncGenerator[Event]:
        if not user_text.strip():
            raise EmptyInputError("user_text must not be empty")

        turn = Turn(user_text)
        if self.guardrail is not None:
            verdict = await self.guardrail.filter_input(user_text)
            if verdict.action != "allow":
                yield guardrail_event("input", verdict.action, verdict.findings)
            if verdict.action == "block":
                return
            turn.user_text = verdict.text
            turn.masked = verdict.action == "redact"

        turn.rag_context = await self._retrieve(turn.user_text)
        self.conversation.add_message(role="user", content=turn.user_text)
        tools_schema = self.registry.get_tools_schema() if self.registry else None
        composer, streamer = self._composer, self._streamer

        yield AssistantStartEvent()
        for step in range(1, self.max_steps + 1):
            if self.reasoning:
                yield StepEvent(index=step, max_steps=self.max_steps)
            prompt = await composer.compose(turn, bool(tools_schema))
            stream = streamer.open(prompt, tools_schema)
            async for event in stream.events():
                yield event
            reply = stream.reply

            if not reply.tool_calls or reply.refused:
                self._finish(turn, reply)
                return

            async for event in self._run_tools(turn, reply, confirm_tool):
                yield event
            if turn.declined:
                return

        async for event in self._conclude(turn):
            yield event

    async def _run_tools(
        self, turn: Turn, reply: Round, confirm_tool: ConfirmTool | None
    ) -> AsyncGenerator[Event]:
        """Record the tool calls and run them, noting a redacted result in `turn`.

        If the user declined any, `turn.declined` names them and the turn ends
        with a short note instead of another model call.
        """
        self.conversation.add_message(
            role="assistant",
            content=reply.message_text,
            tool_calls=reply.tool_calls,
            thought=reply.thought,
        )
        tools = self._tools
        turn.declined = []
        for tc in reply.tool_calls:
            outcome = await tools.run(tc, confirm_tool)
            if outcome.declined:
                turn.declined.append(tc.name)
            async for event in tools.store(outcome.result):
                if isinstance(event, GuardrailEvent) and event.action == "redact":
                    turn.masked = True
                yield event

        if turn.declined:
            names = ", ".join(dict.fromkeys(turn.declined))
            text = f"I didn't run the requested tool: {names}."
            self.conversation.add_message(role="assistant", content=text)
            yield TextChunkEvent(content=text)

    async def _conclude(self, turn: Turn) -> AsyncGenerator[Event]:
        """Force a tool-free answer once the step cap is reached."""
        if self.reasoning:
            yield MaxStepsEvent(max_steps=self.max_steps)
        prompt = await self._composer.compose(turn, False, step_limit=True)
        stream = self._streamer.open(prompt, None)
        async for event in stream.events():
            yield event
        self._finish(turn, stream.reply)

    async def _retrieve(self, user_text: str) -> str:
        if self.retriever is None:
            return ""
        try:
            return await self.retriever.retrieve_context(user_text)
        except (RuntimeError, ValueError, httpx.HTTPError) as exc:
            raise ProviderError("retrieval failed") from exc

    def _finish(self, turn: Turn, reply: Round) -> None:
        """Store the final answer; a guardrail refusal is not the model's, so not graded."""
        answer = reply.text
        self.conversation.add_message(
            role="assistant", content=answer, thought=reply.thought
        )
        if self.recorder is not None and not reply.refused and answer.strip():
            self.recorder.record(turn.user_text, answer, turn.rag_context)

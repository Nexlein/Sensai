from collections.abc import AsyncGenerator

import httpx

from sensai.core.prompt import build_prompt
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, GuardrailEvent, TextChunkEvent, ToolCallEvent
from sensai.domain.models import Conversation, GuardrailFinding, ToolCall
from sensai.domain.protocols import (
    ContextRetriever,
    Guardrail,
    LLMProvider,
    ToolRegistry,
)

TOOL_RESULT_WITHHELD = "[tool result withheld: it contained personal data]"


def _reason(findings: list[GuardrailFinding]) -> str:
    """Which rules fired, e.g. "injection: ignore_instructions; pii: email".

    Rule names only: the matched text is never put in an event or a log.
    """
    rules_by_category: dict[str, list[str]] = {}
    for finding in findings:
        rules_by_category.setdefault(finding.category, []).append(finding.rule)
    return "; ".join(
        f"{category}: {', '.join(dict.fromkeys(rules))}"
        for category, rules in rules_by_category.items()
    )


class ChatEngine:
    def __init__(
        self,
        provider: LLMProvider,
        conversation: Conversation,
        registry: ToolRegistry | None = None,
        retriever: ContextRetriever | None = None,
        guardrail: Guardrail | None = None,
    ) -> None:
        self.provider = provider
        self.conversation = conversation
        self.registry = registry
        self.retriever = retriever
        self.guardrail = guardrail

    async def send(self, user_text: str) -> AsyncGenerator[Event]:
        if not user_text.strip():
            raise EmptyInputError("user_text must not be empty")

        if self.guardrail is not None:
            verdict = await self.guardrail.filter_input(user_text)
            if verdict.action != "allow":
                yield GuardrailEvent(
                    stage="input",
                    action=verdict.action,
                    reason=_reason(verdict.findings),
                )
            if verdict.action == "block":
                return
            # From here on only the filtered text exists: it is what the retriever
            # embeds, what the provider sees and what gets stored in the history.
            user_text = verdict.text

        rag_context = ""
        if self.retriever is not None:
            try:
                rag_context = await self.retriever.retrieve_context(user_text)
            except (RuntimeError, ValueError, httpx.HTTPError) as exc:
                raise ProviderError("retrieval failed") from exc

        self.conversation.add_message(role="user", content=user_text)

        for _ in range(5):
            prompt = build_prompt(self.conversation, rag_context=rag_context)

            chunks: list[str] = []
            tool_calls: list[ToolCallEvent] = []
            stream = self.guardrail.new_output_stream() if self.guardrail else None

            try:
                tools_schema = (
                    self.registry.get_tools_schema() if self.registry else None
                )
                async for event in self.provider.chat_stream(
                    prompt, tools=tools_schema
                ):
                    if isinstance(event, TextChunkEvent):
                        if stream is not None:
                            released = stream.feed(event.content)
                            if not released:
                                continue
                            event = TextChunkEvent(content=released)
                        chunks.append(event.content)
                    elif isinstance(event, ToolCallEvent):
                        tool_calls.append(event)
                    yield event
            except (RuntimeError, httpx.ConnectError) as exc:
                self.conversation.messages.pop()
                raise ProviderError("provider request failed") from exc

            refused = False
            if stream is not None:
                # Text the filter was still holding back (it could have been the
                # start of a PII value) is settled now that the stream is over.
                tail = stream.flush()
                if tail:
                    chunks.append(tail)
                    yield TextChunkEvent(content=tail)
                refused = stream.refused
                if stream.findings:
                    yield GuardrailEvent(
                        stage="output",
                        action="block" if refused else "redact",
                        reason=_reason(stream.findings),
                    )

            # A refused reply is final: its tool calls are dropped, not executed.
            if not tool_calls or refused:
                self.conversation.add_message(role="assistant", content="".join(chunks))
                break

            tcs = [
                ToolCall(name=tc.tool_name, arguments=tc.arguments) for tc in tool_calls
            ]
            self.conversation.add_message(
                role="assistant",
                content="".join(chunks),
                tool_calls=tcs,
            )

            for tc in tcs:
                tool = self.registry.get(tc.name) if self.registry else None
                if not tool:
                    result = f"Error: Tool '{tc.name}' not found in registry."
                else:
                    try:
                        result = await tool.execute(**tc.arguments)
                    except Exception as e:  # noqa: BLE001
                        result = str(e)

                content = str(result)
                if self.guardrail is not None:
                    verdict = await self.guardrail.filter_output(content)
                    if verdict.action != "allow":
                        yield GuardrailEvent(
                            stage="tool",
                            action=verdict.action,
                            reason=_reason(verdict.findings),
                        )
                    content = (
                        TOOL_RESULT_WITHHELD
                        if verdict.action == "block"
                        else verdict.text
                    )

                self.conversation.add_message(role="tool", content=content)

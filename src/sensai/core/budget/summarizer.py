from sensai.domain.events import TextChunkEvent
from sensai.domain.models import Message
from sensai.domain.protocols import LLMProvider

INSTRUCTION = (
    "Condense the conversation below into a compact summary. "
    "Keep facts, decisions, names, file paths and open tasks. "
    "Drop pleasantries. Reply with the summary only."
)


def _render(message: Message) -> str:
    calls = "".join(f" [called {c.name}]" for c in message.tool_calls or [])
    return f"{message.role}: {message.content}{calls}"


class LLMSummarizer:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def summarize(self, messages: list[Message]) -> str:
        prompt = [
            Message(role="system", content=INSTRUCTION),
            Message(role="user", content="\n".join(_render(m) for m in messages)),
        ]
        chunks = [
            event.content
            async for event in self.provider.chat_stream(prompt)
            if isinstance(event, TextChunkEvent)
        ]
        return "".join(chunks).strip()

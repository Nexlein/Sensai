import json

from sensai.domain.models import Message

CHARS_PER_TOKEN = 4
MESSAGE_OVERHEAD = 4


def count_text(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN)


def count_message(message: Message) -> int:
    tokens = MESSAGE_OVERHEAD + count_text(message.content)
    for call in message.tool_calls or []:
        tokens += count_text(call.name + json.dumps(call.arguments))
    return tokens

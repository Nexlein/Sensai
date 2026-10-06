from sensai.domain.models import Message


def group_turns(messages: list[Message]) -> list[list[Message]]:
    """Group messages so a tool call always stays with its results."""
    turns: list[list[Message]] = []
    for message in messages:
        if message.role == "user" or not turns:
            turns.append([])
        turns[-1].append(message)
    return turns


def split_window(
    messages: list[Message], keep_recent_turns: int
) -> tuple[list[Message], list[Message]]:
    turns = group_turns(messages)
    cut = max(len(turns) - keep_recent_turns, 0)
    old = [m for turn in turns[:cut] for m in turn]
    recent = [m for turn in turns[cut:] for m in turn]
    return old, recent

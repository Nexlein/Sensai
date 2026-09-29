from sensai.core.budget.window import group_turns, split_window
from sensai.domain.models import Message, ToolCall


def _exchange(n: int) -> list[Message]:
    return [
        Message(role="user", content=f"q{n}"),
        Message(role="assistant", content=f"a{n}"),
    ]


def _tool_exchange() -> list[Message]:
    return [
        Message(role="user", content="read it"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(name="read_file", arguments={"path": "a"})],
        ),
        Message(role="tool", content="file body"),
        Message(role="assistant", content="done"),
    ]


def test_empty_history():
    assert group_turns([]) == []
    assert split_window([], keep_recent_turns=4) == ([], [])


def test_each_user_message_starts_a_turn():
    messages = _exchange(1) + _exchange(2)

    turns = group_turns(messages)

    assert [len(t) for t in turns] == [2, 2]


def test_tool_call_stays_with_its_result():
    turns = group_turns(_tool_exchange())

    assert len(turns) == 1
    assert [m.role for m in turns[0]] == ["user", "assistant", "tool", "assistant"]


def test_leading_system_message_forms_its_own_turn():
    summary = Message(role="system", content="summary")

    turns = group_turns([summary, *_exchange(1)])

    assert turns[0] == [summary]
    assert len(turns) == 2


def test_fewer_turns_than_window_leaves_old_empty():
    messages = _exchange(1) + _exchange(2)

    old, recent = split_window(messages, keep_recent_turns=4)

    assert old == []
    assert recent == messages


def test_exactly_window_size_leaves_old_empty():
    messages = _exchange(1) + _exchange(2)

    old, recent = split_window(messages, keep_recent_turns=2)

    assert old == []
    assert recent == messages


def test_oldest_turns_go_to_old():
    messages = _exchange(1) + _exchange(2) + _exchange(3)

    old, recent = split_window(messages, keep_recent_turns=1)

    assert old == messages[:4]
    assert recent == messages[4:]


def test_tool_pair_never_split_at_boundary():
    messages = _exchange(1) + _tool_exchange() + _exchange(3)

    old, recent = split_window(messages, keep_recent_turns=2)

    assert old == messages[:2]
    assert recent[0].content == "read it"
    assert [m.role for m in recent[:4]] == ["user", "assistant", "tool", "assistant"]


def test_existing_summary_rolls_into_old():
    summary = Message(role="system", content="summary")
    messages = [summary, *_exchange(1), *_exchange(2)]

    old, recent = split_window(messages, keep_recent_turns=2)

    assert old == [summary]
    assert recent == messages[1:]

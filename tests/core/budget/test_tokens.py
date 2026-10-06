from sensai.core.budget.tokens import MESSAGE_OVERHEAD, count_message, count_text
from sensai.domain.models import Message, ToolCall


def test_empty_text_is_zero():
    assert count_text("") == 0


def test_partial_token_rounds_up():
    assert count_text("a") == 1
    assert count_text("abcd") == 1
    assert count_text("abcde") == 2


def test_message_includes_overhead():
    message = Message(role="user", content="abcd")

    assert count_message(message) == MESSAGE_OVERHEAD + 1


def test_empty_message_costs_only_overhead():
    assert count_message(Message(role="user", content="")) == MESSAGE_OVERHEAD


def test_tool_calls_add_to_count():
    plain = Message(role="assistant", content="ok")
    with_call = Message(
        role="assistant",
        content="ok",
        tool_calls=[ToolCall(name="read_file", arguments={"path": "a.txt"})],
    )

    assert count_message(with_call) > count_message(plain)


def test_multibyte_text_counts_characters():
    assert count_text("é" * 8) == 2

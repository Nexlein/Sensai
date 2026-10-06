import pytest

from sensai.domain.models import ToolCall
from sensai.interfaces.prompts import (
    DETAIL_MAX_LENGTH,
    Option,
    Question,
    tool_confirmation,
    tool_decision,
)


def _question() -> Question[str]:
    return Question(
        title="Pick",
        options=(Option("Alpha", "a"), Option("Beta", "b")),
        cancel_value="none",
    )


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("", "a"),
        ("  ", "a"),
        ("1", "a"),
        ("2", "b"),
        ("3", "none"),
        ("0", "none"),
        ("beta", "b"),
        ("B", "b"),
        ("alp", "none"),
        ("zzz", "none"),
    ],
)
def test_resolve_matches_number_label_or_initial(answer, expected):
    assert _question().resolve(answer) == expected


def test_tool_confirmation_lists_arguments_as_details():
    question = tool_confirmation(
        ToolCall(name="web_search", arguments={"query": "café", "filters": ["a", 1]})
    )

    assert question.title == "Allow web_search?"
    assert [option.label for option in question.options] == ["Yes", "No"]
    assert [option.value for option in question.options] == [True, False]
    assert question.cancel_value is False
    assert question.details == (("query", "café"), ("filters", '["a", 1]'))


def test_tool_confirmation_keeps_details_on_one_short_line():
    long_text = "word\n" * 50
    question = tool_confirmation(ToolCall(name="t", arguments={"text": long_text}))

    value = question.details[0][1]
    assert "\n" not in value
    assert len(value) == DETAIL_MAX_LENGTH
    assert value.endswith("…")


def test_tool_decision_text():
    tc = ToolCall(name="web_search", arguments={})

    assert tool_decision(tc, True) == "✓ allowed web_search"
    assert tool_decision(tc, False) == "✗ declined web_search"

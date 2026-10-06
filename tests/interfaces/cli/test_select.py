import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from sensai.interfaces.cli.select import question_fragments, select
from sensai.interfaces.prompts import Option, Question


def _question() -> Question[str]:
    return Question(
        title="Allow web_search?",
        options=(Option("Yes", "yes"), Option("No", "no")),
        cancel_value="cancel",
        details=(("query", "Sensai"),),
    )


@pytest.mark.parametrize(
    "keys, expected",
    [
        ("\r", "yes"),
        ("\x1b[B\r", "no"),
        ("\x1b[B\x1b[B\r", "yes"),
        ("\x1b[A\r", "no"),
        ("2", "no"),
        ("1", "yes"),
        ("\x03", "cancel"),
        ("\x1b", "cancel"),
    ],
)
async def test_select_returns_option_for_keys(keys, expected):
    with create_pipe_input() as pipe:
        pipe.send_text(keys)
        with create_app_session(input=pipe, output=DummyOutput()):
            assert await select(_question()) == expected


def test_fragments_highlight_current_option():
    text = "".join(fragment[1] for fragment in question_fragments(_question(), 1))

    assert text.startswith("  Allow web_search?\n    query  Sensai\n\n")
    assert "    1. Yes\n" in text
    assert "  ❯ 2. No\n" in text
    assert text.endswith("↑↓ select · enter confirm · esc cancel")

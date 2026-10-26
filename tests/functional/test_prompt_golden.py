"""Golden files: the exact system prompt the model gets on a first turn.

A prompt change then shows up as a reviewable diff instead of slipping in. After a
deliberate change, refresh the files and commit them with it:

    SENSAI_UPDATE_GOLDEN=1 uv run pytest tests/functional/test_prompt_golden.py
"""

import json
import os
from pathlib import Path

import pytest

GOLDEN = Path(__file__).with_name("golden")
PERSONA = Path(__file__).resolve().parents[2] / "personas" / "collecte.md"
# The prompt carries today's date: freeze it so the files stay stable.
pytestmark = pytest.mark.usefixtures("today")


def _system_prompt(context) -> str:
    first_call = context.engine.provider.calls[0]
    return "\n\n---\n\n".join(
        m.content for m in first_call.messages if m.role == "system"
    )


def _check(name: str, actual: str) -> None:
    path = GOLDEN / name
    if os.environ.get("SENSAI_UPDATE_GOLDEN"):
        path.parent.mkdir(exist_ok=True)
        path.write_text(actual, encoding="utf-8")
    assert path.exists(), f"missing {path}: run with SENSAI_UPDATE_GOLDEN=1"
    assert actual == path.read_text(encoding="utf-8"), (
        f"system prompt changed; review, then refresh {path.name}"
    )


@pytest.mark.parametrize(
    ("name", "config"),
    [
        ("system_prompt_default.txt", ""),
        (
            "system_prompt_persona.txt",
            f'[persona]\nenabled = true\nfile = "{PERSONA}"\n',
        ),
    ],
)
async def test_first_turn_system_prompt_matches_its_golden_file(
    open_session, say, name, config
):
    context = await open_session("ok", config=config)

    await say(context, "Bonjour")

    _check(name, _system_prompt(context))


async def test_tool_definitions_sent_to_the_model_match_their_golden_file(
    open_session, say
):
    context = await open_session("ok")

    await say(context, "Bonjour")

    tools = context.engine.provider.calls[0].tools
    _check("tools.json", json.dumps(tools, indent=2, ensure_ascii=False) + "\n")

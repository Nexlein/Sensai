"""Long-term memory: a fact told once is stored, then used in a new conversation."""

import re

import pytest

pytestmark = pytest.mark.live


async def test_fact_told_once_is_used_after_a_new_conversation(live_session, say):
    context = await live_session()

    told = await say(context, "Retiens que je travaille sur le secteur C.")
    print(told.transcript())
    facts = context.structured_memory.list_facts()
    assert any("C" in f.value for f in facts), f"nothing stored: {facts}"

    await say(context, "/new")
    asked = await say(context, "Sur quel secteur je travaille ?")
    print(asked.transcript())

    assert re.search(r"\bC\b", asked.text)


async def test_recall_is_used_when_auto_inject_is_off(live_session, say):
    context = await live_session("[memory]\nauto_inject = false\n")
    context.structured_memory.store_fact("user", "editeur_prefere", "Helix")

    exchange = await say(
        context, "Quel est mon éditeur de texte préféré ? Regarde dans ta mémoire."
    )
    print(exchange.transcript())

    assert "recall_memory" in [c.tool_name for c in exchange.tool_calls]
    assert "Helix" in exchange.text

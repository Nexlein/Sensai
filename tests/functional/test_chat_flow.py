"""A user chatting through a full session: replies, persistence, commands, outages."""

import pytest

from sensai.domain.errors import ProviderError
from sensai.domain.events import AssistantStartEvent, ToolCallEvent
from sensai.providers.mock import ScriptedLLMProvider


async def test_greeting_gets_a_direct_reply_without_any_tool(open_session, say):
    context = await open_session("Bonjour ! Je réponds aux questions sur la collecte.")

    exchange = await say(context, "Bonjour, tu sers à quoi ?")

    assert exchange.text == "Bonjour ! Je réponds aux questions sur la collecte."
    assert exchange.of(AssistantStartEvent)
    assert not exchange.of(ToolCallEvent)
    assert not exchange.confirmations
    roles = [m.role for m in context.engine.conversation.messages]
    assert roles == ["user", "assistant"]


async def test_every_built_in_tool_is_offered_to_the_model(open_session, say):
    context = await open_session("ok")

    await say(context, "salut")

    offered = {t["function"]["name"] for t in context.engine.provider.calls[0].tools}
    assert {
        "read_file",
        "list_dir",
        "write_file",
        "web_search",
        "run_python",
    } <= offered
    assert {"remember_fact", "recall_memory", "forget_fact"} <= offered


async def test_named_session_survives_a_restart(open_session, say):
    saved = await open_session("noted", session_name="tournee")
    await say(saved, "Je suis sur le secteur B.")
    restarted = await open_session("Oui, secteur B.", session_name="tournee")

    history = [m.content for m in restarted.engine.conversation.messages]
    assert history == ["Je suis sur le secteur B.", "noted"]
    await say(restarted, "Tu te souviens de mon secteur ?")
    sent = [m.content for m in restarted.engine.provider.calls[0].messages]
    assert "Je suis sur le secteur B." in sent


async def test_model_outage_is_an_error_and_the_next_turn_works(open_session, say):
    context = await open_session()  # empty script: the first call fails

    with pytest.raises(ProviderError):
        await say(context, "Bonjour")
    assert context.engine.conversation.messages == []

    context.engine.provider = ScriptedLLMProvider("Me revoilà.")
    exchange = await say(context, "Bonjour")
    assert exchange.text == "Me revoilà."


async def test_new_command_starts_an_empty_conversation(open_session, say):
    context = await open_session("première réponse")
    await say(context, "première question")

    exchange = await say(context, "/new")

    assert exchange.result.message
    assert context.engine.conversation.messages == []


async def test_config_set_rebuilds_the_provider_of_the_running_session(
    open_session, say
):
    context = await open_session()
    scripted = context.engine.provider

    await say(context, "/config set model qwen3:8b")
    exchange = await say(context, "/config get model")

    assert "qwen3:8b" in exchange.result.message
    assert context.config.model == "qwen3:8b"
    assert context.engine.provider is not scripted


async def test_unknown_command_is_answered_and_nothing_reaches_the_model(
    open_session, say
):
    context = await open_session()

    exchange = await say(context, "/frobnicate")

    assert exchange.result.message == "Unknown command: /frobnicate"
    assert context.engine.provider.calls == []

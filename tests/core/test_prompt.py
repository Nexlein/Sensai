from sensai.core.prompt import build_prompt
from sensai.domain.models import Conversation, Persona


def test_persona_system_instruction_prepended_once():
    conversation = Conversation()
    conversation.add_message("user", "hello")
    persona = Persona(
        id="p1", name="Bot", description="desc", system_instruction="You are a bot."
    )

    messages = build_prompt(conversation, persona)

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[0].content == "You are a bot."


def test_no_persona_no_system_message():
    conversation = Conversation()
    conversation.add_message("user", "hello")

    messages = build_prompt(conversation)

    assert len(messages) == 1
    assert all(m.role != "system" for m in messages)


def test_message_order_preserved():
    conversation = Conversation()
    conversation.add_message("user", "first")
    conversation.add_message("assistant", "second")
    conversation.add_message("user", "third")
    persona = Persona(id="p1", name="Bot", description="desc", system_instruction="sys")

    messages = build_prompt(conversation, persona)

    assert [m.content for m in messages] == ["sys", "first", "second", "third"]

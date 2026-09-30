from sensai.core.prompt import PRIVACY_NOTE, build_prompt
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


def test_privacy_note_is_a_system_message_and_off_by_default():
    conversation = Conversation()
    conversation.add_message("user", "hello")

    assert all(m.role != "system" for m in build_prompt(conversation))

    messages = build_prompt(conversation, privacy_note=True)

    assert [m.role for m in messages] == ["system", "user"]
    assert messages[0].content == PRIVACY_NOTE
    assert "placeholders" in PRIVACY_NOTE


def test_privacy_note_goes_after_persona_and_before_retrieved_context():
    conversation = Conversation()
    conversation.add_message("user", "hello")
    persona = Persona(id="p", name="Bot", description="d", system_instruction="sys")

    messages = build_prompt(
        conversation, persona, rag_context="a fact", privacy_note=True
    )

    assert [m.role for m in messages] == ["system", "system", "system", "user"]
    assert messages[0].content == "sys"
    assert messages[1].content == PRIVACY_NOTE
    assert "a fact" in messages[2].content


def test_privacy_note_is_not_added_to_the_conversation():
    conversation = Conversation()
    conversation.add_message("user", "hello")

    build_prompt(conversation, privacy_note=True)

    assert [m.role for m in conversation.messages] == ["user"]

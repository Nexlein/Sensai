from sensai.domain.models import Conversation, Message, Persona


def build_prompt(
    conversation: Conversation, persona: Persona | None = None
) -> list[Message]:
    messages = list(conversation.messages)
    if persona is not None:
        system_message = Message(role="system", content=persona.system_instruction)
        return [system_message, *messages]
    return messages

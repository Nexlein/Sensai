from sensai.core.turn import Round, Turn


def test_turn_starts_unmasked_with_nothing_declined():
    turn = Turn("hi")

    assert (turn.user_text, turn.rag_context, turn.masked, turn.declined) == (
        "hi",
        "",
        False,
        [],
    )


def test_round_text_joins_chunks():
    assert Round(chunks=["a", "b"]).text == "ab"


def test_round_thought_puts_native_reasoning_before_text_thought():
    reply = Round(native_thoughts=["deep ", "thought"], text_thought=" aloud ")

    assert reply.thought == "deep thought\naloud"


def test_round_thought_is_none_when_empty():
    assert Round().thought is None


def test_round_message_text_is_empty_when_text_became_a_thought():
    assert Round(chunks=["x"], text_thought="x").message_text == ""
    assert Round(chunks=["x"]).message_text == "x"

import pytest

from sensai.eval.guardrails import (
    MAX_SPACED_PII,
    REFUSAL_TEXT,
    PiiOutputStream,
    RegexGuardrail,
    redact_pii,
)

VALID_CARD = "4111 1111 1111 1111"
VALID_IBAN = "FR14 2004 1010 0505 0001 3M02 606"
VALID_NIR = "1 84 12 76 451 089 46"


PROSE = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 3
STREAM_TEXTS = [
    f"Contact john.doe@example.com for details. {PROSE}",
    f"{PROSE}Pay to {VALID_IBAN} before friday. {PROSE}",
    f"Call 06 12 34 56 78 or +33 6 12 34 56 78, card {VALID_CARD}.",
    f"{PROSE}My nir is {VALID_NIR}",
    "abc0612345678 is not a phone, 0612345678 is.",
    f"a@b.io{PROSE}c@d.io",
    "x" * 500 + " y@z.io",
    f"Reach {'u' * 60}@example.com please. {PROSE}",
    PROSE,
    "",
]


def _stream(text: str, size: int, **kwargs) -> tuple[str, PiiOutputStream]:
    stream = PiiOutputStream(**kwargs)
    out = "".join(stream.feed(text[i : i + size]) for i in range(0, len(text), size))
    return out + stream.flush(), stream


@pytest.mark.parametrize("text", STREAM_TEXTS)
@pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 16, 100, 10_000])
def test_stream_matches_one_shot_redaction_for_any_chunking(text, size):
    streamed, _ = _stream(text, size)
    assert streamed == redact_pii(text)[0]


def test_stream_never_emits_pii_even_mid_stream():
    text = f"Write to john.doe@example.com now. {PROSE}"
    stream = PiiOutputStream()
    seen = ""
    for char in text:
        seen += stream.feed(char)
        assert "john" not in seen and "example.com" not in seen
    seen += stream.flush()
    assert "[EMAIL]" in seen


def test_stream_releases_text_before_the_end():
    stream = PiiOutputStream()
    released = stream.feed(PROSE)
    assert released  # not everything is held back
    assert len(PROSE) - len(released) <= MAX_SPACED_PII + len("elit. ")


def test_stream_holds_a_partial_email_until_it_completes():
    stream = PiiOutputStream()
    assert stream.feed("mail: john.doe@exam") == ""
    assert stream.feed("ple.com and more") + stream.flush() == "mail: [EMAIL] and more"


def test_stream_does_not_hold_back_text_written_without_spaces():
    # Found by review: with no whitespace the whole 320-char email window was kept,
    # so Chinese text arrived in bursts 320 characters behind the model.
    text = "这是一个没有空格的中文句子，" * 40
    stream = PiiOutputStream()
    emitted = 0
    worst_lag = 0
    for count, char in enumerate(text, start=1):
        emitted += len(stream.feed(char))
        worst_lag = max(worst_lag, count - emitted)

    assert worst_lag <= MAX_SPACED_PII
    assert emitted + len(stream.flush()) == len(text)


@pytest.mark.parametrize("size", [1, 2, 5, 11])
def test_stream_masks_pii_glued_to_text_without_spaces(size):
    text = (
        "这是一个没有空格的中文句子，" * 8
        + "邮箱john.doe@example.com谢谢"
        + "好的" * 30
    )
    streamed, _ = _stream(text, size)

    assert streamed == redact_pii(text)[0]
    assert "john" not in streamed
    assert "[EMAIL]" in streamed


def test_stream_still_holds_a_long_partial_email_after_chinese_text():
    stream = PiiOutputStream()
    released = stream.feed("联系" + "u" * 60 + "@exam")
    assert "u" not in released
    assert released + stream.feed("ple.com谢谢") + stream.flush() == "联系[EMAIL]谢谢"


def test_stream_handles_empty_chunks():
    stream = PiiOutputStream()
    assert stream.feed("") == ""
    assert stream.flush() == ""


def test_stream_findings_list_each_redaction_once():
    _, stream = _stream(f"a@b.io and {VALID_CARD}. {PROSE}", 4)
    assert [(f.rule, f.category) for f in stream.findings] == [
        ("email", "pii"),
        ("credit_card", "pii"),
    ]


def test_stream_block_emits_clean_prefix_then_refusal_and_swallows_the_rest():
    text = f"Sure! The address is a@b.io and more text. {PROSE}"
    streamed, stream = _stream(text, 3, action="block")
    assert streamed == "Sure! The address is " + REFUSAL_TEXT
    assert stream.refused
    assert [f.rule for f in stream.findings] == ["email"]
    assert stream.feed("anything") == ""
    assert stream.flush() == ""


def test_stream_block_without_pii_passes_text_through():
    streamed, stream = _stream(PROSE, 5, action="block")
    assert streamed == PROSE
    assert not stream.refused
    assert stream.findings == []


def test_guardrail_creates_independent_streams():
    guardrail = RegexGuardrail()
    first, second = guardrail.new_output_stream(), guardrail.new_output_stream()
    first.feed("a@b.io")
    assert second.feed("hello") + second.flush() == "hello"


@pytest.mark.parametrize("pad", range(70))
def test_stream_cut_landing_anywhere_around_a_word_never_changes_the_result(pad):
    # The digits are not a phone number: they are glued to "abc". If the buffer were
    # ever cut between "c" and "0", the remainder would wrongly look like one.
    text = "hi abc0612345678 real 0612345678 " + "z" * pad
    stream = PiiOutputStream()
    out = stream.feed(text) + stream.flush()
    assert out == redact_pii(text)[0]
    assert "abc0612345678" in out


def test_card_followed_by_cvv_is_redacted_when_streamed_in_small_chunks():
    text = f"Use card {VALID_CARD} 123 for the order. " + PROSE
    for size in (1, 3, 7):
        streamed, _ = _stream(text, size)
        assert streamed == redact_pii(text)[0]
        assert "4111" not in streamed

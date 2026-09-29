import time
from itertools import pairwise

import pytest

from sensai.eval.guardrails import find_injection, find_pii, redact_pii

VALID_CARD = "4111 1111 1111 1111"
VALID_IBAN = "FR14 2004 1010 0505 0001 3M02 606"
VALID_NIR = "1 84 12 76 451 089 46"


def test_finds_email_and_ignores_trailing_punctuation():
    text = "Write to john.doe+work@example.co.uk."
    (match,) = find_pii(text)
    assert match.rule == "email"
    assert text[match.start : match.end] == "john.doe+work@example.co.uk"


def test_does_not_flag_obfuscated_or_incomplete_email():
    assert find_pii("john at example dot com") == []
    assert find_pii("@handle and user@localhost") == []


@pytest.mark.parametrize(
    "phone",
    [
        "06 12 34 56 78",
        "0612345678",
        "+33 6 12 34 56 78",
        "0033612345678",
        "+1 415 555 2671",
    ],
)
def test_finds_phone_numbers(phone):
    (match,) = find_pii(f"call {phone} now")
    assert match.rule == "phone"


def test_credit_card_requires_valid_luhn():
    assert [m.rule for m in find_pii(f"card {VALID_CARD}")] == ["credit_card"]
    assert find_pii("order 4111 1111 1111 1112") == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("card 4111 1111 1111 1111 123", "card [CARD] 123"),  # card + CVV
        # A number before the card. "105 4111 1111 1111" is Luhn-valid by chance
        # (a trap): masking it would leave the card's last group in clear.
        ("105 4111 1111 1111 1111", "105 [CARD]"),
        ("4111-1111-1111-1111-123", "[CARD]-123"),  # hyphen separated
        ("4111 1111 1111 1111 555123", "[CARD] 555123"),
        ("pay 3782 822463 10005 456", "pay [CARD] 456"),  # 15-digit card + extra
    ],
)
def test_card_is_found_inside_a_longer_run_of_digit_groups(text, expected):
    assert redact_pii(text)[0] == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("我的IBAN是FR1420041010050500013M02606谢谢", "我的IBAN是[IBAN]谢谢"),
        ("邮箱john.doe@example.com谢谢", "邮箱[EMAIL]谢谢"),
        ("电话0612345678谢谢", "电话[PHONE]谢谢"),
        ("卡号4111 1111 1111 1111谢谢", "卡号[CARD]谢谢"),
        ("社保号1 84 12 76 451 089 46谢谢", "社保号[SSN]谢谢"),
        ("私のメールはjohn@example.comです", "私のメールは[EMAIL]です"),
    ],
)
def test_pii_glued_to_text_without_spaces_is_still_masked(text, expected):
    assert redact_pii(text)[0] == expected


def test_ascii_word_boundaries_do_not_break_latin_text():
    # Glued to an ASCII letter it is still not a card / phone number.
    assert find_pii("ref4111111111111111") == []
    assert find_pii("abc0612345678") == []
    assert redact_pii("café: 0612345678")[0] == "café: [PHONE]"


def test_digits_glued_to_a_card_are_not_cut_apart():
    # No group boundary inside the run, so it is one long number, not a card.
    assert find_pii("4111111111111111123") == []


def test_card_recovery_does_not_invent_cards_in_ordinary_numbers():
    text = "reference 1234 5678 9012 3456 789 confirmed"
    assert find_pii(text) == []


def test_iban_requires_valid_checksum():
    assert [m.rule for m in find_pii(f"iban {VALID_IBAN}")] == ["iban"]
    assert find_pii("iban GB82 WEST 1234 5698 7654 33") == []


def test_ssn_requires_valid_key():
    assert [m.rule for m in find_pii(f"nir {VALID_NIR}")] == ["ssn"]
    assert find_pii("nir 1 84 12 76 451 089 47") == []


def test_plain_numbers_and_prose_are_left_alone():
    text = "In 2024 we shipped 1234567 units, ticket #98765, version 3.14.7."
    assert find_pii(text) == []


def test_overlapping_matches_keep_highest_priority_rule():
    # The 15 digits of a valid NIR could also loosely look like a card number.
    matches = find_pii(VALID_NIR)
    assert [m.rule for m in matches] == ["ssn"]


def test_multiple_matches_are_sorted_and_non_overlapping():
    text = f"{VALID_IBAN} then mail a@b.io and {VALID_CARD}"
    matches = find_pii(text)
    assert [m.rule for m in matches] == ["iban", "email", "credit_card"]
    assert all(a.end <= b.start for a, b in pairwise(matches))


# --- redaction --------------------------------------------------------------


def test_redact_replaces_each_match_with_its_token():
    text = f"Mail a@b.io, card {VALID_CARD}, phone 06 12 34 56 78."
    redacted, matches = redact_pii(text)
    assert redacted == "Mail [EMAIL], card [CARD], phone [PHONE]."
    assert len(matches) == 3


def test_redact_without_pii_returns_text_unchanged():
    redacted, matches = redact_pii("nothing sensitive here")
    assert redacted == "nothing sensitive here"
    assert matches == []


def test_redact_is_idempotent():
    once, _ = redact_pii(f"a@b.io {VALID_IBAN}")
    twice, matches = redact_pii(once)
    assert twice == once
    assert matches == []


@pytest.mark.parametrize(
    "hostile",
    [
        "1-" * 100_000,
        "1 " * 100_000,
        "a@" * 100_000,
        "a." * 100_000,
        "ignore " * 20_000,
        "give me your " * 20_000,
        "donne-moi ton " * 20_000,
    ],
)
def test_detectors_stay_linear_on_hostile_input(hostile):
    start = time.perf_counter()
    find_pii(hostile)
    find_injection(hostile)
    assert time.perf_counter() - start < 2.0


def test_email_with_over_long_local_part_is_still_redacted():
    text = "a" * 100 + "@example.com"
    redacted, matches = redact_pii(text)
    assert [m.rule for m in matches] == ["email"]
    assert "example.com" not in redacted
    assert redacted.endswith("[EMAIL]")

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sensai.eval.guardrails import iban_valid, luhn_valid, nir_valid

VALID_CARD = "4111 1111 1111 1111"
VALID_IBAN = "FR14 2004 1010 0505 0001 3M02 606"
VALID_NIR = "1 84 12 76 451 089 46"


@pytest.mark.parametrize("number", ["4111111111111111", "378282246310005"])
def test_luhn_accepts_valid_numbers(number):
    assert luhn_valid(number)


@pytest.mark.parametrize("number", ["4111111111111112", "", "41a1", "0000000000000001"])
def test_luhn_rejects_invalid_numbers(number):
    assert not luhn_valid(number)


@pytest.mark.parametrize(
    "iban", ["FR1420041010050500013M02606", VALID_IBAN, "GB82 WEST 1234 5698 7654 32"]
)
def test_iban_accepts_valid_numbers(iban):
    assert iban_valid(iban)


@pytest.mark.parametrize(
    "iban", ["GB82 WEST 1234 5698 7654 33", "FR14", "", "FR14-2004-1010-0505-0001"]
)
def test_iban_rejects_invalid_numbers(iban):
    assert not iban_valid(iban)


def test_nir_accepts_valid_key():
    assert nir_valid(VALID_NIR)


def test_nir_accepts_corsican_department():
    assert nir_valid("1 85 07 2A 123 456 65")


def test_nir_rejects_wrong_key_and_wrong_length():
    assert not nir_valid("1 84 12 76 451 089 47")
    assert not nir_valid("1 84 12 76 451 089")


# Properties: checked on generated numbers, not only on the examples above.

DIGITS = "0123456789"


def _with_luhn_digit(body: str) -> str:
    return next(body + d for d in DIGITS if luhn_valid(body + d))


@given(st.text(DIGITS, min_size=1, max_size=30))
def test_luhn_accepts_exactly_one_check_digit_per_body(body):
    assert len([d for d in DIGITS if luhn_valid(body + d)]) == 1


@given(st.text(DIGITS, min_size=1, max_size=30), st.data())
def test_luhn_catches_every_single_digit_typo(body, data):
    number = _with_luhn_digit(body)
    i = data.draw(st.integers(0, len(number) - 1))
    typo = data.draw(st.sampled_from(DIGITS).filter(lambda d: d != number[i]))

    assert not luhn_valid(number[:i] + typo + number[i + 1 :])


def _iban(country: str, bban: str) -> str:
    numeric = "".join(str(int(c, 36)) for c in bban + country + "00")
    return f"{country}{98 - int(numeric) % 97:02d}{bban}"


IBAN_PARTS = (
    st.text("ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=2, max_size=2),
    st.text(DIGITS + "ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=11, max_size=30),
)


@given(*IBAN_PARTS)
def test_iban_with_computed_check_digits_is_valid_in_any_layout(country, bban):
    iban = _iban(country, bban)
    spaced = " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))

    assert iban_valid(iban)
    assert iban_valid(spaced.lower())


@given(*IBAN_PARTS, st.data())
def test_iban_catches_every_single_digit_typo(country, bban, data):
    iban = _iban(country, bban)
    positions = [i for i, c in enumerate(iban) if c.isdigit()]
    i = data.draw(st.sampled_from(positions))
    typo = data.draw(st.sampled_from(DIGITS).filter(lambda d: d != iban[i]))

    assert not iban_valid(iban[:i] + typo + iban[i + 1 :])


@given(st.text(DIGITS, min_size=13, max_size=13))
def test_nir_accepts_its_own_key_and_no_other(body):
    key = 97 - int(body) % 97

    assert nir_valid(f"{body}{key:02d}")
    assert not nir_valid(f"{body}{(key % 97) + 1:02d}")

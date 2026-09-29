import pytest

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

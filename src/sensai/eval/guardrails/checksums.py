"""Checksum validators for PII formats that have one."""

import re


def luhn_valid(number: str) -> bool:
    """Luhn checksum over a digit string (credit/debit cards)."""
    if not number.isdigit():
        return False
    total = 0
    for index, char in enumerate(reversed(number)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def iban_valid(iban: str) -> bool:
    """ISO 13616 mod-97 check. Length is bounded but not checked per country."""
    compact = iban.replace(" ", "").upper()
    if not 15 <= len(compact) <= 34 or not compact.isalnum():
        return False
    rearranged = compact[4:] + compact[:4]
    # Letters map to 10..35, digits stay as they are (base 36 does exactly that).
    numeric = "".join(str(int(char, 36)) for char in rearranged)
    return int(numeric) % 97 == 1


def nir_valid(nir: str) -> bool:
    """French social security number (NIR): 13 digits + 2-digit key.

    key = 97 - (first 13 digits mod 97). Corsican departments 2A/2B are
    computed as 19/18.
    """
    compact = nir.replace(" ", "").upper()
    if len(compact) != 15:
        return False
    body, key = compact[:13], compact[13:]
    body = body[:5] + body[5:7].replace("2A", "19").replace("2B", "18") + body[7:]
    if not body.isdigit() or not key.isdigit():
        return False
    return 97 - int(body) % 97 == int(key)


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def card_valid(value: str) -> bool:
    digits = digits_only(value)
    return 13 <= len(digits) <= 19 and luhn_valid(digits)


def card_span(value: str) -> tuple[int, int] | None:
    """Find a valid card inside a longer run of digit groups.

    "4111 1111 1111 1111 123" (card + CVV) is one 19-digit run that fails Luhn,
    yet its first four groups are a card. Candidates are runs of whole groups
    (split on space/hyphen), so digits glued together are never cut apart. The
    longest valid run wins: in "105 4111 1111 1111 1111" the 15 digits
    "105 4111 1111 1111" also pass Luhn by chance, but taking them would leave
    the last "1111" of the real card unmasked.
    """
    groups = [m.span() for m in re.finditer(r"[^ -]+", value)]
    best: tuple[int, tuple[int, int]] | None = None
    for first in range(len(groups)):
        for last in range(first, len(groups)):
            start, end = groups[first][0], groups[last][1]
            if not card_valid(value[start:end]):
                continue
            digits = len(digits_only(value[start:end]))
            if best is None or digits > best[0]:
                best = (digits, (start, end))
    return best[1] if best else None

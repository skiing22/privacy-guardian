"""Checksum and format validators (FR-06). They cut false positives from regex."""

import re

_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)

# 4th PAN char = holder type (P=person, C=company, H=HUF, F=firm, ...)
_PAN_HOLDER_TYPES = frozenset("PCHFATBLJG")


def digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


def verhoeff_valid(number: str) -> bool:
    """True if the last digit is a correct Verhoeff check digit (used by Aadhaar)."""
    if not number.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(payload: str) -> str:
    """Check digit to append to `payload`. Used by tests and the synthetic data generator."""
    if not payload.isdigit():
        raise ValueError("payload must be digits")
    c = 0
    for i, ch in enumerate(reversed(payload)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def luhn_valid(number: str) -> bool:
    """Luhn mod-10 check (payment cards)."""
    if not number.isdigit() or len(number) < 2:
        return False
    total = 0
    for i, ch in enumerate(reversed(number)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def aadhaar_valid(raw: str) -> bool:
    """12 digits, first digit 2-9, valid Verhoeff checksum."""
    n = digits_only(raw)
    return len(n) == 12 and n[0] not in "01" and verhoeff_valid(n)


def card_valid(raw: str) -> bool:
    n = digits_only(raw)
    return 13 <= len(n) <= 19 and luhn_valid(n)


def pan_valid(raw: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", raw)) and raw[3] in _PAN_HOLDER_TYPES


def ifsc_valid(raw: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", raw))


def indian_mobile_valid(raw: str) -> bool:
    n = digits_only(raw)
    if len(n) == 12 and n.startswith("91"):
        n = n[2:]
    elif len(n) == 11 and n.startswith("0"):
        n = n[1:]
    return len(n) == 10 and n[0] in "6789"


def ipv4_valid(raw: str) -> bool:
    parts = raw.split(".")
    return len(parts) == 4 and all(
        p.isdigit() and int(p) <= 255 and (p == "0" or not p.startswith("0")) for p in parts
    )

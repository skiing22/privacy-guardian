from hypothesis import given
from hypothesis import strategies as st

from app.detectors import validators as v

eleven_digits = st.text(alphabet="0123456789", min_size=11, max_size=11).filter(
    lambda s: s[0] not in "01"
)


def make_aadhaar(payload: str) -> str:
    return payload + v.verhoeff_check_digit(payload)


def test_verhoeff_known_vector() -> None:
    assert v.verhoeff_check_digit("236") == "3"
    assert v.verhoeff_valid("2363")
    assert not v.verhoeff_valid("2364")


@given(eleven_digits)
def test_generated_aadhaar_is_valid(payload: str) -> None:
    assert v.aadhaar_valid(make_aadhaar(payload))


@given(eleven_digits, st.integers(0, 11), st.integers(1, 9))
def test_verhoeff_catches_any_single_digit_error(payload: str, pos: int, delta: int) -> None:
    good = make_aadhaar(payload)
    bad = good[:pos] + str((int(good[pos]) + delta) % 10) + good[pos + 1 :]
    assert not v.verhoeff_valid(bad)


def test_aadhaar_rules() -> None:
    a = make_aadhaar("23456789012")
    assert v.aadhaar_valid(f"{a[:4]} {a[4:8]} {a[8:]}")
    assert not v.aadhaar_valid("1" + a[1:])  # cannot start with 0 or 1
    assert not v.aadhaar_valid(a[:-1])


def test_luhn() -> None:
    assert v.luhn_valid("4111111111111111")
    assert not v.luhn_valid("4111111111111112")
    assert v.card_valid("4111 1111 1111 1111")


def test_pan() -> None:
    assert v.pan_valid("ABCPE1234F")
    assert not v.pan_valid("ABCXE1234F")  # X is not a valid holder type
    assert not v.pan_valid("abcpe1234f")


def test_ifsc() -> None:
    assert v.ifsc_valid("SBIN0001234")
    assert not v.ifsc_valid("SBIN1001234")  # 5th char must be 0


def test_mobile() -> None:
    assert v.indian_mobile_valid("98765 43210")
    assert v.indian_mobile_valid("+91 9876543210")
    assert v.indian_mobile_valid("09876543210")
    assert not v.indian_mobile_valid("5876543210")


def test_ipv4() -> None:
    assert v.ipv4_valid("192.168.1.10")
    assert not v.ipv4_valid("256.1.1.1")
    assert not v.ipv4_valid("01.2.3.4")

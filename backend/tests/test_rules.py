from app.detectors.rules import RuleDetector
from app.detectors.types import PiiType
from app.detectors.validators import verhoeff_check_digit

det = RuleDetector()
AADHAAR = "23456789012" + verhoeff_check_digit("23456789012")
AADHAAR_SPACED = f"{AADHAAR[:4]} {AADHAAR[4:8]} {AADHAAR[8:]}"


def types_found(text: str) -> set[PiiType]:
    return {s.pii_type for s in det.detect(text)}


def test_finds_all_types_with_correct_offsets() -> None:
    text = (
        f"Rahul (rahul.s@gmail.com, +91 98765 43210) has Aadhaar {AADHAAR_SPACED}, "
        "PAN ABCPE1234F, IFSC SBIN0001234, card 4111-1111-1111-1111, IP 10.0.0.12."
    )
    spans = det.detect(text)
    assert {s.pii_type for s in spans} >= {
        PiiType.EMAIL,
        PiiType.PHONE,
        PiiType.AADHAAR,
        PiiType.PAN,
        PiiType.IFSC,
        PiiType.CARD,
        PiiType.IP_ADDRESS,
    }
    for s in spans:
        assert text[s.start : s.end] == s.text


def test_invalid_checksum_is_dropped() -> None:
    bad_aadhaar = AADHAAR[:-1] + str((int(AADHAAR[-1]) + 1) % 10)
    assert PiiType.AADHAAR not in types_found(f"id {bad_aadhaar}")
    assert PiiType.CARD not in types_found("card 4111 1111 1111 1112")


def test_no_match_inside_longer_number() -> None:
    assert PiiType.PHONE not in types_found("order 1239876543210999")


def test_plain_text_has_no_pii() -> None:
    assert det.detect("The meeting is on Monday in room 204.") == []

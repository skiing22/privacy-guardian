"""Each case is a real M1 error from docs/results/handwritten-v1.md."""

from hypothesis import given
from hypothesis import strategies as st

from app.detectors.context import ContextDetector
from app.detectors.rules import RuleDetector
from app.detectors.types import PiiType, Span
from app.fusion.fuse import fuse, resolve

rules = RuleDetector()
T = PiiType


def ner(text: str, part: str, t: PiiType, score: float = 0.9, nth: int = 0) -> Span:
    i = -1
    for _ in range(nth + 1):
        i = text.index(part, i + 1)
    return Span(i, i + len(part), part, t, score, "ner")


def out(text: str, spans: list[Span]) -> list[tuple[str, PiiType]]:
    return [(s.text, s.pii_type) for s in fuse(text, spans)]


def test_validated_rule_beats_higher_scoring_model_guess() -> None:
    t = "Aadhaar 5284-7163-9206 linked to mobile 7012345678 successfully."
    spans = rules.detect(t) + [ner(t, "7012345678", T.GOV_ID, 0.99)]
    assert ("7012345678", T.PHONE) in out(t, spans)


def test_agreeing_sources_raise_confidence() -> None:
    t = "call 9847012345"
    r = rules.detect(t)
    fused = fuse(t, r + [ner(t, "9847012345", T.PHONE, 0.8)])
    assert fused[0].score > max(r[0].score, 0.8)
    assert fused[0].source == "ner+rules"


def test_keywords_and_masked_values_dropped() -> None:
    t = "My Aadhaar is 3948 1726 3059. Your A/c XX4521 is debited."
    spans = rules.detect(t) + [ner(t, "Aadhaar", T.PERSON), ner(t, "XX4521", T.GOV_ID)]
    assert out(t, spans) == [("3948 1726 3059", T.AADHAAR)]


def test_context_kills_harmless_numbers() -> None:
    cases = [
        ("Your OTP is 482913. Do not share it.", "482913", T.ADDRESS),
        ("Order #4029384756 has been shipped.", "4029384756", T.GOV_ID),
        ("see you in room 204 today", "204", T.ADDRESS),
        ("fixes the login bug on Android 14.", "14", T.AGE),
        ("Card ending 1111 was used.", "1111", T.ADDRESS),
    ]
    for t, part, typ in cases:
        assert out(t, [ner(t, part, typ, 0.95)]) == [], t


def test_context_keeps_real_numbers() -> None:
    t = "Admitted at age 34 today"
    assert out(t, [ner(t, "34", T.AGE, 0.9)]) == [("34", T.AGE)]


def test_split_indian_address_is_rebuilt() -> None:
    t = "Send the documents to 22, Nehru Nagar, Bhopal - 462003."
    spans = [
        ner(t, "22,", T.ADDRESS),
        ner(t, "Nehru", T.LOCATION),
        ner(t, "Nagar", T.ADDRESS),
        ner(t, "Bhopal", T.ADDRESS),
        ner(t, "462003", T.ADDRESS),
    ]
    assert out(t, spans) == [
        ("22, Nehru Nagar", T.ADDRESS),
        ("Bhopal", T.LOCATION),
        ("462003", T.ADDRESS),
    ]


def test_flat_and_park_merge_but_city_stays() -> None:
    t = "They live at Flat 3B, Green Park, Hyderabad."
    spans = [
        ner(t, "Flat 3B", T.ADDRESS),
        ner(t, "Green Park", T.LOCATION),
        ner(t, "Hyderabad", T.LOCATION),
    ]
    assert out(t, spans) == [("Flat 3B, Green Park", T.ADDRESS), ("Hyderabad", T.LOCATION)]


def test_city_and_pin_stay_apart() -> None:
    t = "Address: 14 MG Road, Kochi 682016."
    spans = [
        ner(t, "14 MG Road", T.ADDRESS),
        ner(t, "Kochi", T.LOCATION),
        ner(t, "682016", T.ADDRESS),
    ]
    assert len(out(t, spans)) == 3


def test_split_licence_number_merges() -> None:
    t = "Driving licence KL11 20190012345 belongs to Joseph."
    spans = [ner(t, "KL11", T.GOV_ID), ner(t, "20190012345", T.GOV_ID)]
    assert out(t, spans) == [("KL11 20190012345", T.GOV_ID)]


def test_weekday_joins_date() -> None:
    t = "on Monday, 16 November 2026."
    assert out(t, [ner(t, "16 November 2026", T.DATE)]) == [("Monday, 16 November 2026", T.DATE)]


def test_context_detector_finds_lowercase_gender() -> None:
    t = "Rahul Das, 45 yrs, male, from Siliguri."
    assert [(s.text, s.pii_type) for s in ContextDetector().detect(t)] == [("male", T.GENDER)]


spans_strategy = st.lists(
    st.tuples(st.integers(0, 80), st.integers(1, 15), st.sampled_from(list(PiiType)),
              st.floats(0.0, 1.0), st.sampled_from(["rules", "ner", "context"])),
    max_size=25,
)  # fmt: skip


@given(spans_strategy)
def test_resolve_output_never_overlaps(raw: list[tuple[int, int, PiiType, float, str]]) -> None:
    text = "x" * 100
    spans = [Span(s, s + n, text[s : s + n], t, sc, src) for s, n, t, sc, src in raw]
    res = resolve(spans)
    for a, b in zip(res, res[1:], strict=False):
        assert a.end <= b.start
    for r in res:
        assert 0.0 <= r.score <= 1.0

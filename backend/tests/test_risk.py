import pytest

from app.detectors.types import PiiType, Span
from app.fusion.risk import RiskLevel, assess

T = PiiType


def spans(text: str, parts: list[tuple[str, PiiType]]) -> list[Span]:
    out = []
    for part, t in parts:
        i = text.index(part)
        out.append(Span(i, i + len(part), part, t, 0.9, "ner"))
    return out


def test_nothing_left_is_low_risk() -> None:
    r = assess("all clean", [])
    assert r.level is RiskLevel.LOW and r.est_matches == pytest.approx(1.4e9)


def test_direct_identifier_dominates() -> None:
    t = "Priya, female"
    r = assess(t, spans(t, [("Priya", T.PERSON), ("female", T.GENDER)]))
    assert r.level is RiskLevel.DIRECT and r.score == 1.0


def test_sweeney_combination_is_high_risk() -> None:
    # gender + DOB + PIN: the classic trio
    t = "DOB: 23-10-2002, Gender: Male, PIN 673601"
    r = assess(t, spans(t, [("23-10-2002", T.DATE), ("Male", T.GENDER), ("673601", T.ADDRESS)]))
    assert r.clues == ("dob", "gender", "pin")
    assert r.level is RiskLevel.HIGH and r.est_matches < 5


def test_city_and_gender_alone_is_low() -> None:
    t = "a woman from Kochi"
    r = assess(t, spans(t, [("woman", T.GENDER), ("Kochi", T.LOCATION)]))
    assert r.level is RiskLevel.LOW


def test_generalizing_age_lowers_risk() -> None:
    t1, t2 = "age 34, male, Siliguri", "age 30-35, male, Siliguri"
    exact = assess(t1, spans(t1, [("34", T.AGE), ("male", T.GENDER), ("Siliguri", T.LOCATION)]))
    banded = assess(t2, spans(t2, [("30-35", T.AGE), ("male", T.GENDER), ("Siliguri", T.LOCATION)]))
    assert banded.est_matches > exact.est_matches
    assert banded.score < exact.score


def test_appointment_date_is_not_a_clue() -> None:
    t = "appointment on 20/11/2026"
    assert assess(t, spans(t, [("20/11/2026", T.DATE)])).clues == ()


def test_street_address_is_high() -> None:
    t = "lives at 14 MG Road"
    assert assess(t, spans(t, [("14 MG Road", T.ADDRESS)])).level is RiskLevel.HIGH

import pytest

from app.detectors.label_map import map_spans
from app.detectors.types import PiiType


def spans_text(text: str, spans: list[tuple[int, int, PiiType]]) -> list[tuple[str, PiiType]]:
    return [(text[s:e], t) for s, e, t in spans]


def label(text: str, part: str, lab: str) -> tuple[int, int, str]:
    i = text.index(part)
    return (i, i + len(part), lab)


def test_given_and_surname_merge_into_one_person() -> None:
    t = "Dr. Rahul Sharma called."
    raw = [label(t, "Dr.", "TITLE"), label(t, "Rahul", "GIVENNAME"), label(t, "Sharma", "SURNAME")]
    assert spans_text(t, map_spans(t, raw)) == [("Rahul Sharma", PiiType.PERSON)]


def test_address_parts_merge_but_city_stays_separate() -> None:
    t = "Lives at 12, MG Road, 560001 in Bengaluru."
    raw = [
        label(t, "12", "BUILDINGNUM"),
        label(t, "MG Road", "STREET"),
        label(t, "560001", "ZIPCODE"),
        label(t, "Bengaluru", "CITY"),
    ]
    assert spans_text(t, map_spans(t, raw)) == [
        ("12, MG Road, 560001", PiiType.ADDRESS),
        ("Bengaluru", PiiType.LOCATION),
    ]


def test_two_people_far_apart_do_not_merge() -> None:
    t = "Rahul met Priya."
    raw = [label(t, "Rahul", "GIVENNAME"), label(t, "Priya", "GIVENNAME")]
    assert len(map_spans(t, raw)) == 2


def test_ids_never_merge() -> None:
    t = "IDs A123 B456"
    raw = [label(t, "A123", "IDCARDNUM"), label(t, "B456", "PASSPORTNUM")]
    assert len(map_spans(t, raw)) == 2


def test_unknown_label_fails_loudly() -> None:
    with pytest.raises(KeyError):
        map_spans("x", [(0, 1, "NEWLABEL")])

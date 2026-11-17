from app.detectors.types import PiiType, Span
from app.fusion.linking import link
from app.fusion.normalize import normalize

T = PiiType


def sp(text: str, t: PiiType = T.PERSON) -> Span:
    return Span(0, len(text), text, t, 0.9, "ner")


def groups(spans: list[Span]) -> list[set[str]]:
    return [{spans[m].text for m in e.mentions} for e in link(spans)]


def test_short_mentions_join_full_name() -> None:
    spans = [sp("Rahul Sharma"), sp("Rahul"), sp("Mr. Sharma"), sp("R. Sharma"), sp("Priya")]
    assert groups(spans) == [{"Rahul Sharma", "Rahul", "Mr. Sharma", "R. Sharma"}, {"Priya"}]


def test_ambiguous_surname_is_not_linked() -> None:
    spans = [sp("Vikram Reddy"), sp("Sneha Reddy"), sp("Reddy")]
    ents = link(spans)
    assert len(ents) == 3
    assert [e.ambiguous for e in ents] == [False, False, True]


def test_same_phone_written_two_ways() -> None:
    spans = [sp("98470 12345", T.PHONE), sp("+91 9847012345", T.PHONE), sp("09847012345", T.PHONE)]
    ents = link(spans)
    assert len(ents) == 1 and ents[0].id == "PHONE_1"


def test_different_types_never_link() -> None:
    spans = [sp("Kochi", T.LOCATION), sp("Kochi", T.PERSON)]
    assert len(link(spans)) == 2


def test_ids_count_per_type_and_canonical_is_longest() -> None:
    ents = link([sp("Rahul"), sp("Rahul Sharma"), sp("a@b.com", T.EMAIL), sp("Priya Iyer")])
    assert [(e.id, e.canonical) for e in ents] == [
        ("PERSON_1", "Rahul Sharma"),
        ("EMAIL_1", "a@b.com"),
        ("PERSON_2", "Priya Iyer"),
    ]


def test_normalize() -> None:
    assert normalize("+91 98470-12345", T.PHONE) == "9847012345"
    assert normalize("abcpe1234f", T.PAN) == "ABCPE1234F"
    assert normalize("Dr. Lakshmi  Menon", T.PERSON) == "lakshmi menon"

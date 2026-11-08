from app.detectors.types import PiiType, Span
from app.fusion.baseline import greedy_resolve


def sp(s: int, e: int, t: PiiType, score: float, src: str) -> Span:
    return Span(s, e, "x" * (e - s), t, score, src)


def test_higher_score_wins_overlap() -> None:
    a = sp(0, 14, PiiType.AADHAAR, 0.99, "rules")
    b = sp(0, 14, PiiType.GOV_ID, 0.90, "ner")
    c = sp(20, 25, PiiType.PERSON, 0.95, "ner")
    assert greedy_resolve([b, c, a]) == [a, c]


def test_rules_win_ties() -> None:
    a = sp(0, 5, PiiType.PHONE, 0.95, "ner")
    b = sp(0, 5, PiiType.PHONE, 0.95, "rules")
    assert greedy_resolve([a, b])[0].source == "rules"

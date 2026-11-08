import pytest

from app.detectors.ner_labels import IGNORE, align_labels, build_label_list, span_scores
from app.detectors.types import PiiType


def test_label_list_shape() -> None:
    labels = build_label_list()
    assert labels[0] == "O"
    assert "B-PERSON" in labels and "I-PERSON" in labels
    assert len(labels) == len(set(labels))
    assert not any("TITLE" in lab or "TIME" in lab for lab in labels)


def test_align_first_subtoken_and_bio() -> None:
    # text: "Call Rahul Sharma now"
    #        0    5     11     18
    labels = build_label_list()
    l2i = {lab: i for i, lab in enumerate(labels)}
    offsets = [(0, 0), (0, 4), (5, 8), (8, 10), (11, 17), (18, 21), (0, 0)]
    word_ids = [None, 0, 1, 1, 2, 3, None]  # "Rahul" split into 2 sub-tokens
    spans = [(5, 17, PiiType.PERSON)]
    got = align_labels(offsets, word_ids, spans, l2i)
    assert got == [
        IGNORE,
        l2i["O"],
        l2i["B-PERSON"],
        IGNORE,
        l2i["I-PERSON"],
        l2i["O"],
        IGNORE,
    ]


def test_span_scores() -> None:
    gold = [{(0, 5, "PERSON"), (10, 20, "EMAIL")}]
    pred = [{(0, 5, "PERSON"), (10, 19, "EMAIL")}]  # email boundary off by one
    s = span_scores(gold, pred)
    assert s["PERSON"]["f1"] == 1.0
    assert s["EMAIL"]["precision"] == 0.0
    assert s["ALL"]["precision"] == pytest.approx(0.5)
    assert s["ALL"]["recall"] == pytest.approx(0.5)

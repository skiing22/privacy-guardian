from pathlib import Path

import pytest

from app.detectors.validators import aadhaar_valid, card_valid
from app.eval.goldset import load, parse_line

GOLD = Path(__file__).resolve().parents[2] / "data" / "eval" / "handwritten_v1.txt"


def test_parse_line_offsets() -> None:
    ex = parse_line("Hi [[Priya|PERSON]] from [[Kochi|LOCATION]].")
    assert ex.text == "Hi Priya from Kochi."
    assert {ex.text[s:e] for s, e, _ in ex.spans} == {"Priya", "Kochi"}


def test_bad_label_fails() -> None:
    with pytest.raises(ValueError):
        parse_line("x [[y|NAME]]")


def test_gold_file_is_valid() -> None:
    examples = load(GOLD)
    assert len(examples) >= 30
    for ex in examples:
        for s, e, t in ex.spans:
            value = ex.text[s:e]
            assert value == value.strip()
            if t == "AADHAAR":
                assert aadhaar_valid(value), value
            if t == "CARD":
                assert card_valid(value), value

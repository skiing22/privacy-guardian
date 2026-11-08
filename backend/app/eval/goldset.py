"""Parse the hand-written gold set markup (ADR-0012).

`Hi [[Priya|PERSON]] from [[Kochi|LOCATION]]` -> text without markup + span offsets.
Writing markup instead of raw offsets keeps the file easy to edit by hand.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from app.detectors.types import PiiType

_MARK = re.compile(r"\[\[(.+?)\|([A-Z_]+)\]\]")


@dataclass(frozen=True)
class GoldExample:
    text: str
    spans: frozenset[tuple[int, int, str]]


def parse_line(line: str) -> GoldExample:
    out: list[str] = []
    spans: set[tuple[int, int, str]] = set()
    pos = 0
    length = 0
    for m in _MARK.finditer(line):
        before = line[pos : m.start()]
        out.append(before)
        length += len(before)
        value, label = m.group(1), m.group(2)
        PiiType(label)  # fail loudly on a typo in the label
        spans.add((length, length + len(value), label))
        out.append(value)
        length += len(value)
        pos = m.end()
    out.append(line[pos:])
    text = "".join(out)
    if "[[" in text or "]]" in text:
        raise ValueError(f"broken markup: {line!r}")
    return GoldExample(text, frozenset(spans))


def load(path: Path) -> list[GoldExample]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [parse_line(ln) for ln in lines if ln.strip() and not ln.startswith("#")]

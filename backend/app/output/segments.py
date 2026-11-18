"""Rebuild the cleaned text from the original document and the stored decisions
(DATABASE 2.1: nothing is stored twice).

Round r's offsets refer to the text that round received: the original for round 1, the
previous round's output after that. We replay each round on a list of pieces. Every piece
remembers which item replaced it (`item`) and which parsed part of the file it belongs
to (`part`, None for the separators the parser added), so the writers can put each
cleaned part back where it came from (a DOCX paragraph, a CSV cell).
"""

from dataclasses import dataclass, replace

from app.detectors.types import PiiType
from app.parsers.base import ParsedDoc
from app.policy.actions import Action, render


class OutputError(Exception):
    pass


@dataclass(frozen=True)
class Item:
    idx: int
    round: int  # 1-based
    start: int
    end: int
    pii_type: PiiType
    action: Action
    token: str | None


@dataclass(frozen=True)
class Piece:
    text: str
    item: int | None
    part: int | None


@dataclass(frozen=True)
class Rebuilt:
    pieces: tuple[Piece, ...]
    outputs: dict[int, str]  # item idx -> exact replacement text

    @property
    def text(self) -> str:
        return "".join(p.text for p in self.pieces)

    def part_texts(self, n: int) -> list[str]:
        out = [""] * n
        for p in self.pieces:
            if p.part is not None:
                out[p.part] += p.text
        return out

    def segments(self) -> list[dict[str, object]]:
        """API 4.9 `cleaned_segments`: adjacent pieces with the same item merged."""
        segs: list[dict[str, object]] = []
        for p in self.pieces:
            if segs and segs[-1]["item_idx"] == p.item and p.item is None:
                segs[-1]["text"] = str(segs[-1]["text"]) + p.text
            elif p.text:
                segs.append({"text": p.text, "item_idx": p.item})
        return segs


def initial_pieces(doc: ParsedDoc) -> list[Piece]:
    pieces: list[Piece] = []
    pos = 0
    for k, seg in enumerate(doc.segments):
        if seg.start > pos:
            pieces.append(Piece(doc.text[pos : seg.start], None, None))
        pieces.append(Piece(doc.text[seg.start : seg.end], None, k))
        pos = seg.end
    if pos < len(doc.text):
        pieces.append(Piece(doc.text[pos:], None, None))
    return pieces


def _split(pieces: list[Piece], cuts: set[int]) -> list[Piece]:
    out: list[Piece] = []
    pos = 0
    for p in pieces:
        a, b = pos, pos + len(p.text)
        inner = sorted(c for c in cuts if a < c < b)
        last = a
        for c in [*inner, b]:
            if c > last:
                out.append(replace(p, text=p.text[last - a : c - a]))
            last = c
        pos = b
    return out


def apply_round(pieces: list[Piece], items: list[Item], outputs: dict[int, str]) -> list[Piece]:
    text = "".join(p.text for p in pieces)
    items = sorted(items, key=lambda it: it.start)
    for a, b in zip(items, items[1:], strict=False):
        if b.start < a.end:
            raise OutputError("overlapping items in one round")
    if items and items[-1].end > len(text):
        raise OutputError("item outside the text")
    cuts = {x for it in items for x in (it.start, it.end)}
    pieces = _split(pieces, cuts)
    by_start = {it.start: it for it in items}
    out: list[Piece] = []
    pos, i = 0, 0
    while i < len(pieces):
        p = pieces[i]
        it = by_start.get(pos)
        if it is None:
            out.append(p)
            pos += len(p.text)
            i += 1
            continue
        covered: list[Piece] = []
        while i < len(pieces) and pos < it.end:
            covered.append(pieces[i])
            pos += len(pieces[i].text)
            i += 1
        value = text[it.start : it.end]
        new = render(it.action, it.pii_type, value, it.token or f"{it.pii_type.value}_?")
        outputs[it.idx] = new
        part = next((c.part for c in covered if c.part is not None), None)
        out.append(Piece(new, it.idx, part))
    return out


def rebuild(doc: ParsedDoc, items: list[Item]) -> Rebuilt:
    pieces = initial_pieces(doc)
    outputs: dict[int, str] = {}
    for r in sorted({it.round for it in items}):
        pieces = apply_round(pieces, [it for it in items if it.round == r], outputs)
    return Rebuilt(tuple(pieces), outputs)

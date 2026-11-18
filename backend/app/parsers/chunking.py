"""Chunking for long text (FR-03).

DistilBERT reads at most 512 tokens; longer input would be cut off silently. We split the
text into overlapping windows, run the detector on each, shift offsets back, and repair the
edges:
- a span that touches a cut edge (not the real start/end of the text) may be cut in half,
  so it is dropped; the overlap guarantees the neighbouring window holds it whole
  (for entities shorter than the overlap);
- the same span found in two windows is kept once (highest score).
"""

from dataclasses import dataclass, replace
from typing import Protocol

from app.detectors.types import Span


class Detector(Protocol):
    def detect(self, text: str) -> list[Span]: ...


@dataclass(frozen=True)
class Chunk:
    start: int
    text: str

    @property
    def end(self) -> int:
        return self.start + len(self.text)


def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> list[Chunk]:
    """~1500 chars stays under 512 tokens for English/Indian text (about 3-4 chars/token).
    Cuts at whitespace when possible so words are not split."""
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")
    if len(text) <= max_chars:
        return [Chunk(0, text)]
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + max_chars - overlap, end)
            if cut > start:
                end = cut
        chunks.append(Chunk(start, text[start:end]))
        if end >= len(text):
            break
        nxt = end - overlap
        sp = text.find(" ", nxt, end)  # start the next window on a word boundary
        start = sp + 1 if sp != -1 else nxt
    return chunks


class ChunkedDetector:
    def __init__(self, inner: Detector, max_chars: int = 1500, overlap: int = 200) -> None:
        self.inner, self.max_chars, self.overlap = inner, max_chars, overlap

    def detect(self, text: str) -> list[Span]:
        chunks = chunk_text(text, self.max_chars, self.overlap)
        best: dict[tuple[int, int, str], Span] = {}
        for ch in chunks:
            for s in self.inner.detect(ch.text):
                g = replace(s, start=s.start + ch.start, end=s.end + ch.start)
                cut_left = ch.start > 0 and g.start == ch.start
                cut_right = ch.end < len(text) and g.end == ch.end
                if cut_left or cut_right:
                    continue
                k = (g.start, g.end, g.pii_type.value)
                if k not in best or g.score > best[k].score:
                    best[k] = g
        return sorted(best.values(), key=lambda s: (s.start, s.end))

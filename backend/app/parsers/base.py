"""Parsed document with an offset map back to where each piece came from (FR-01, FR-02)."""

from dataclasses import dataclass, field

MAX_BYTES = 10 * 1024 * 1024  # FR-01: 10 MB


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Segment:
    """Characters [start, end) of the joined text came from `loc` in the source file."""

    start: int
    end: int
    loc: str  # "page 2", "paragraph 5", "table 1 r2c3", "row 4, col email"


@dataclass(frozen=True)
class ParsedDoc:
    text: str
    fmt: str
    segments: tuple[Segment, ...] = field(default=())

    def locate(self, offset: int) -> str | None:
        """Where in the original file a character offset came from (binary search)."""
        lo, hi = 0, len(self.segments) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            s = self.segments[mid]
            if offset < s.start:
                hi = mid - 1
            elif offset >= s.end:
                lo = mid + 1
            else:
                return s.loc
        return None


class TextBuilder:
    """Joins pieces with a separator and records a Segment for each."""

    def __init__(self, sep: str = "\n") -> None:
        self.sep = sep
        self.parts: list[str] = []
        self.segments: list[Segment] = []
        self.length = 0

    def add(self, piece: str, loc: str) -> None:
        if not piece:
            return
        if self.parts:
            self.parts.append(self.sep)
            self.length += len(self.sep)
        self.segments.append(Segment(self.length, self.length + len(piece), loc))
        self.parts.append(piece)
        self.length += len(piece)

    def build(self, fmt: str) -> ParsedDoc:
        return ParsedDoc("".join(self.parts), fmt, tuple(self.segments))

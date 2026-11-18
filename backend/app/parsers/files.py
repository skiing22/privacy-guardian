"""TXT, PDF, DOCX and CSV parsers (FR-01 to FR-04)."""

import csv
import io
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.detectors.types import PiiType, Span
from app.parsers.base import MAX_BYTES, ParsedDoc, ParseError, TextBuilder


def decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("cp1252", errors="replace")


def parse_txt(data: bytes) -> ParsedDoc:
    b = TextBuilder()
    for i, line in enumerate(decode_text(data).splitlines(), 1):
        b.add(line, f"line {i}")
    return b.build("txt")


def parse_pdf(data: bytes) -> ParsedDoc:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [p.extract_text() or "" for p in reader.pages]
    except Exception as e:  # pypdf raises many types on broken files
        raise ParseError(f"cannot read PDF: {e}") from e
    if not any(p.strip() for p in pages):
        raise ParseError("PDF has no text layer (scanned image?); OCR is out of scope")
    b = TextBuilder(sep="\n\n")
    for i, page in enumerate(pages, 1):
        b.add(page.strip(), f"page {i}")
    return b.build("pdf")


def parse_docx(data: bytes) -> ParsedDoc:
    import docx

    try:
        d = docx.Document(io.BytesIO(data))
    except Exception as e:
        raise ParseError(f"cannot read DOCX: {e}") from e
    b = TextBuilder()
    for i, p in enumerate(d.paragraphs, 1):
        b.add(p.text, f"paragraph {i}")
    for t, table in enumerate(d.tables, 1):
        for r, row in enumerate(table.rows, 1):
            for c, cell in enumerate(row.cells, 1):
                b.add(cell.text, f"table {t} r{r}c{c}")
    return b.build("docx")


def parse_csv(data: bytes) -> ParsedDoc:
    """Each cell becomes "header: value", so the header gives context ("phone: 98470...")."""
    rows = list(csv.reader(io.StringIO(decode_text(data))))
    if not rows:
        raise ParseError("empty CSV")
    header, body = rows[0], rows[1:]
    b = TextBuilder()
    for r, row in enumerate(body, 2):
        for c, value in enumerate(row):
            name = header[c] if c < len(header) else f"col{c + 1}"
            if value.strip():
                b.add(f"{name}: {value}", f"row {r}, col {name}")
    return b.build("csv")


PARSERS: dict[str, Callable[[bytes], ParsedDoc]] = {
    ".txt": parse_txt,
    ".md": parse_txt,
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".csv": parse_csv,
}


def parse_bytes(data: bytes, filename: str) -> ParsedDoc:
    if len(data) > MAX_BYTES:
        raise ParseError(f"file too large: {len(data)} bytes (max {MAX_BYTES})")
    ext = Path(filename).suffix.lower()
    if ext not in PARSERS:
        raise ParseError(f"unsupported file type: {ext or 'none'}")
    return PARSERS[ext](data)


def parse_file(path: str | Path) -> ParsedDoc:
    p = Path(path)
    return parse_bytes(p.read_bytes(), p.name)


# ---------- FR-04: classify whole CSV columns ----------


@dataclass(frozen=True)
class ColumnVerdict:
    column: str
    pii_type: PiiType | None
    share: float  # share of sampled non-empty cells where that type was found
    sampled: int


def classify_columns(
    data: bytes, detect: Callable[[str], list[Span]], sample: int = 50, min_share: float = 0.5
) -> list[ColumnVerdict]:
    """Sample up to `sample` rows; a column is PII type T if T is found in >= min_share of
    its cells. Lets a user protect a whole column at once instead of cell by cell."""
    rows = list(csv.reader(io.StringIO(decode_text(data))))
    if not rows:
        return []
    header, body = rows[0], rows[1 : 1 + sample]
    out: list[ColumnVerdict] = []
    for c, name in enumerate(header):
        cells = [r[c] for r in body if c < len(r) and r[c].strip()]
        votes: Counter[PiiType] = Counter()
        for v in cells:
            text = f"{name}: {v}"
            found = {s.pii_type for s in detect(text) if s.start >= len(name) + 2}
            votes.update(found)
        if cells and votes:
            t, n = votes.most_common(1)[0]
            share = n / len(cells)
            out.append(
                ColumnVerdict(name, t if share >= min_share else None, round(share, 3), len(cells))
            )
        else:
            out.append(ColumnVerdict(name, None, 0.0, len(cells)))
    return out

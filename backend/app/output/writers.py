"""Write the cleaned parts back in the input's format (FR-29, D4: PDF -> .txt).

Each writer walks the original file in the same order as its parser, so part k of the
parsed document is the k-th piece of text the parser took from the file.
Known limits: DOCX headers, footers and comments are not parsed, so they are not
cleaned (they are dropped from the output instead, see `_write_docx`); a replaced DOCX
paragraph keeps the paragraph style but loses run-level formatting.
"""

import csv
import io
from dataclasses import dataclass

from app.output.segments import OutputError, Rebuilt
from app.parsers.base import ParsedDoc
from app.parsers.files import decode_text


@dataclass(frozen=True)
class CleanedFile:
    data: bytes
    content_type: str
    extension: str


CONTENT_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _write_lines(original: bytes, doc: ParsedDoc, parts: list[str]) -> bytes:
    text = decode_text(original)
    lines = text.splitlines()
    for k, seg in enumerate(doc.segments):
        n = int(seg.loc.removeprefix("line "))
        lines[n - 1] = parts[k]
    nl = _newline(text)  # keep Windows line endings for Windows files
    end = nl if text.endswith(("\n", "\r")) else ""
    return (nl.join(lines) + end).encode()


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _write_csv(original: bytes, parts: list[str]) -> bytes:
    source = decode_text(original)
    rows = list(csv.reader(io.StringIO(source)))
    header = rows[0]
    k = 0
    for row in rows[1:]:
        for c, value in enumerate(row):
            if not value.strip():
                continue
            name = header[c] if c < len(header) else f"col{c + 1}"
            cleaned = parts[k]
            prefix = f"{name}: "
            row[c] = cleaned[len(prefix) :] if cleaned.startswith(prefix) else cleaned
            k += 1
    if k != len(parts):
        raise OutputError("CSV cells do not match the parsed parts")
    buf = io.StringIO()
    csv.writer(buf, lineterminator=_newline(source)).writerows(rows)
    return buf.getvalue().encode()


def _write_docx(original: bytes, parts: list[str]) -> bytes:
    import docx

    d = docx.Document(io.BytesIO(original))
    k = 0
    for p in d.paragraphs:
        if p.text:
            if parts[k] != p.text:
                p.text = parts[k]
            k += 1
    for table in d.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text:
                    if parts[k] != cell.text:
                        cell.text = parts[k]
                    k += 1
    if k != len(parts):
        raise OutputError("DOCX blocks do not match the parsed parts")
    # Not scanned, so never shipped: headers, footers (could hold names or ids).
    for section in d.sections:
        for hf in (section.header, section.footer, section.first_page_header,
                   section.first_page_footer, section.even_page_header,
                   section.even_page_footer):  # fmt: skip
            if not hf.is_linked_to_previous:
                for p in hf.paragraphs:
                    p.text = ""
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def write(fmt: str, original: bytes, doc: ParsedDoc, rebuilt: Rebuilt) -> CleanedFile:
    parts = rebuilt.part_texts(len(doc.segments))
    if fmt in ("txt", "md"):
        return CleanedFile(_write_lines(original, doc, parts), CONTENT_TYPES[fmt], fmt)
    if fmt == "pdf":  # D4: PDF in, text out
        return CleanedFile(rebuilt.text.encode(), CONTENT_TYPES["txt"], "txt")
    if fmt == "csv":
        return CleanedFile(_write_csv(original, parts), CONTENT_TYPES["csv"], "csv")
    if fmt == "docx":
        return CleanedFile(_write_docx(original, parts), CONTENT_TYPES["docx"], "docx")
    raise OutputError(f"unknown format {fmt}")

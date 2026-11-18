import io
import re

import docx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.detectors.rules import RuleDetector
from app.detectors.types import PiiType, Span
from app.parsers.base import MAX_BYTES, ParseError
from app.parsers.chunking import ChunkedDetector, chunk_text
from app.parsers.files import classify_columns, parse_bytes


def make_pdf(pages: list[str]) -> bytes:
    """Smallest valid PDF with one text line per page (built by hand, no extra deps)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    kids = []
    for text in pages:
        n = len(objs) + 1
        kids.append(f"{n} 0 R")
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {n + 1} 0 R "
            "/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 "
            "/BaseFont /Helvetica >> >> >> >>"
        )
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def make_docx() -> bytes:
    d = docx.Document()
    d.add_paragraph("Employee: Rahul Sharma")
    d.add_paragraph("Mobile 98470 12345")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "PAN"
    t.cell(0, 1).text = "ABCPE1234F"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ---------- parsers ----------


def test_txt_and_offset_map() -> None:
    doc = parse_bytes(b"hello\nCall 98470 12345\n", "a.txt")
    i = doc.text.index("98470")
    assert doc.locate(i) == "line 2"


def test_pdf_pages_mapped() -> None:
    doc = parse_bytes(make_pdf(["Name Rahul Sharma", "Mobile 9847012345"]), "x.pdf")
    assert "Rahul Sharma" in doc.text and "9847012345" in doc.text
    assert doc.locate(doc.text.index("9847012345")) == "page 2"
    spans = RuleDetector().detect(doc.text)
    assert [s.pii_type for s in spans] == [PiiType.PHONE]


def test_docx_paragraphs_and_tables() -> None:
    doc = parse_bytes(make_docx(), "x.docx")
    assert doc.locate(doc.text.index("98470")) == "paragraph 2"
    assert doc.locate(doc.text.index("ABCPE1234F")) == "table 1 r1c2"


def test_csv_cells_get_header_context() -> None:
    data = b"name,mobile\nRahul,9847012345\nPriya,9447012345\n"
    doc = parse_bytes(data, "x.csv")
    assert "mobile: 9847012345" in doc.text
    assert doc.locate(doc.text.index("9447012345")) == "row 3, col mobile"


def test_csv_column_classification() -> None:
    data = b"id,mobile,city\n1,9847012345,Kochi\n2,9447012345,Pune\n3,not given,Delhi\n"
    verdicts = {v.column: v for v in classify_columns(data, RuleDetector().detect)}
    assert verdicts["mobile"].pii_type is PiiType.PHONE
    assert verdicts["mobile"].share == pytest.approx(2 / 3, abs=1e-3)
    assert verdicts["id"].pii_type is None


def test_limits_and_bad_files() -> None:
    with pytest.raises(ParseError, match="too large"):
        parse_bytes(b"x" * (MAX_BYTES + 1), "a.txt")
    with pytest.raises(ParseError, match="unsupported"):
        parse_bytes(b"x", "a.exe")
    with pytest.raises(ParseError, match="cannot read PDF"):
        parse_bytes(b"not a pdf", "a.pdf")


def test_cp1252_fallback() -> None:
    assert parse_bytes("café".encode("cp1252"), "a.txt").text == "café"


# ---------- chunking ----------


class WordDetector:
    """Finds a fixed word; stands in for NER on one chunk."""

    def __init__(self, word: str) -> None:
        self.word = word

    def detect(self, text: str) -> list[Span]:
        return [
            Span(m.start(), m.end(), m.group(), PiiType.PERSON, 0.9, "ner")
            for m in re.finditer(re.escape(self.word), text)
        ]


def test_short_text_is_one_chunk() -> None:
    assert len(chunk_text("short text")) == 1


def test_chunks_cover_text_and_overlap() -> None:
    text = " ".join(f"w{i}" for i in range(2000))
    chunks = chunk_text(text, 300, 60)
    assert chunks[0].start == 0 and chunks[-1].end == len(text)
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.start < a.end  # overlapping
        assert len(a.text) <= 300


@settings(max_examples=60)
@given(st.integers(0, 4000))
def test_entity_found_once_wherever_it_falls(pos: int) -> None:
    filler = " ".join(["lorem"] * 900)
    pos = min(pos, len(filler))
    pos = filler.rfind(" ", 0, pos) + 1 if pos else 0
    text = filler[:pos] + "Venkataraman " + filler[pos:]
    spans = ChunkedDetector(WordDetector("Venkataraman"), 300, 60).detect(text)
    assert [(s.start, s.text) for s in spans] == [(pos, "Venkataraman")]

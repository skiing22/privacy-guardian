"""Output rebuild and writers: joined segments equal the graph output, every format."""

import csv
import io
import re

import docx
import pytest

from app.detectors.types import PiiType
from app.graph.build import build_graph, result_of, start_scan
from app.output.segments import Item, OutputError, rebuild
from app.output.writers import write
from app.parsers.files import parse_bytes, parse_csv, parse_docx, parse_txt
from app.policy.actions import Action, actions_for_type
from tests.test_graph import deps

T = PiiType


def items_from(res) -> list[Item]:  # type: ignore[no-untyped-def]
    out, idx = [], 0
    for rec in res.history:
        for k, (sp, d) in enumerate(zip(rec.spans, rec.decisions, strict=True)):
            tok = rec.tokens[k] if rec.tokens else None
            out.append(Item(idx, rec.round + 1, sp.start, sp.end, sp.pii_type, d.action, tok))
            idx += 1
    return out


def run(text: str, hits: list[tuple[str, PiiType, float]], **kw: object):  # type: ignore[no-untyped-def]
    return result_of(start_scan(build_graph(deps(hits, review_threshold=0.0, **kw)), text, "t"))


def test_rebuild_matches_graph_output_one_round() -> None:
    raw = b"Patient: Rahul Sharma\n\nCall 98470 12345 or rahul@example.com\n"
    doc = parse_txt(raw)
    res = run(doc.text, [("Rahul Sharma", T.PERSON, 0.95)])
    rb = rebuild(doc, items_from(res))
    assert rb.text == res.output
    assert "".join(str(s["text"]) for s in rb.segments()) == res.output
    marked = [s for s in rb.segments() if s["item_idx"] is not None]
    assert marked and all(rb.outputs[int(str(s["item_idx"]))] == s["text"] for s in marked)
    cleaned = write("txt", raw, doc, rb).data.decode()
    assert "\n\n" in cleaned and cleaned.endswith("\n")  # blank line and ending kept
    assert "Rahul" not in cleaned and "98470 12345" not in cleaned


def test_rebuild_matches_graph_output_multi_round() -> None:
    text = "Anil met Rahul Sharma. Later Anil called."
    doc = parse_txt(text.encode())
    # "Anil" only found with low confidence -> missed in round 1, caught by the verifier
    res = run(doc.text, [("Rahul Sharma", T.PERSON, 0.95), ("Anil", T.PERSON, 0.4)])
    assert res.rounds >= 2
    rb = rebuild(doc, items_from(res))
    assert rb.text == res.output and "Anil" not in rb.text


def test_csv_writer_keeps_shape() -> None:
    raw = b"name,phone,city\nRahul Sharma,98470 12345,Kochi\nPriya,,Pune\n"
    doc = parse_csv(raw)
    res = run(doc.text, [("Rahul Sharma", T.PERSON, 0.95), ("Priya", T.PERSON, 0.95)])
    rb = rebuild(doc, items_from(res))
    assert rb.text == res.output
    rows = list(csv.reader(io.StringIO(write("csv", raw, doc, rb).data.decode())))
    assert rows[0] == ["name", "phone", "city"] and len(rows) == 3
    assert rows[2][1] == ""  # empty cell stays empty
    assert "Rahul Sharma" not in rows[1][0] and re.match(r"PERSON_", rows[1][0])


def test_docx_writer_paragraphs_and_tables() -> None:
    d = docx.Document()
    d.add_paragraph("Patient: Rahul Sharma")
    d.add_paragraph("")
    d.add_paragraph("Phone 98470 12345")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Priya"
    t.cell(0, 1).text = "ok"
    d.sections[0].header.paragraphs[0].text = "Confidential: Rahul Sharma"
    buf = io.BytesIO()
    d.save(buf)
    raw = buf.getvalue()
    doc = parse_docx(raw)
    res = run(doc.text, [("Rahul Sharma", T.PERSON, 0.95), ("Priya", T.PERSON, 0.95)])
    rb = rebuild(doc, items_from(res))
    out = docx.Document(io.BytesIO(write("docx", raw, doc, rb).data))
    body = [p.text for p in out.paragraphs]
    assert body[1] == "" and "Rahul" not in " ".join(body) and "98470 12345" not in body[2]
    assert "Priya" not in out.tables[0].cell(0, 0).text and out.tables[0].cell(0, 1).text == "ok"
    assert "Rahul" not in out.sections[0].header.paragraphs[0].text  # unscanned: removed


def test_pdf_becomes_txt() -> None:
    doc = parse_txt(b"Rahul Sharma")
    rb = rebuild(doc, [Item(0, 1, 0, 12, T.PERSON, Action.REDACT, None)])
    f = write("pdf", b"", doc, rb)
    assert f.extension == "txt" and f.data == b"[REDACTED]"


def test_overlap_and_out_of_range_rejected() -> None:
    doc = parse_txt(b"abcdefgh")
    with pytest.raises(OutputError):
        rebuild(doc, [Item(0, 1, 0, 4, T.PERSON, Action.REDACT, None),
                      Item(1, 1, 2, 6, T.PERSON, Action.REDACT, None)])  # fmt: skip
    with pytest.raises(OutputError):
        rebuild(doc, [Item(0, 1, 0, 40, T.PERSON, Action.REDACT, None)])


def test_item_across_line_break_collapses_into_first_line() -> None:
    raw = b"Rahul\nSharma\n"
    doc = parse_bytes(raw, "a.txt")
    rb = rebuild(doc, [Item(0, 1, 0, 12, T.PERSON, Action.REDACT, None)])
    assert write("txt", raw, doc, rb).data == b"[REDACTED]\n\n"


def test_actions_for_type() -> None:
    assert actions_for_type(T.AGE) == [Action.KEEP, Action.GENERALIZE, Action.REDACT]
    assert actions_for_type(T.AADHAAR) == [
        Action.KEEP, Action.MASK, Action.PSEUDONYMIZE, Action.REDACT,
    ]  # fmt: skip

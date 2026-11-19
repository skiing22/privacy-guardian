"""QA pass (step 14): edge cases, failures and regressions found by exploratory testing.
Each test names the bug it guards (docs/results/qa-2026-11-20.md)."""

import io
import sqlite3
from pathlib import Path

import docx
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import event

from app.detectors.types import PiiType, Span
from app.fusion.fuse import fuse
from app.output.segments import Item, rebuild
from app.parsers.files import parse_txt
from app.policy.actions import Action
from tests.api_helpers import ORIGIN, Api, api

HITS = [("Rahul Sharma", PiiType.PERSON, 0.95), ("Priya Nair", PiiType.PERSON, 0.95)]


def done_scan(a: Api, **kw: object) -> str:
    r = a.post("/api/v1/scans", **kw)
    assert r.status_code == 202, r.text
    a.drain()
    sid: str = r.json()["id"]
    st_ = a.http.get(f"/api/v1/scans/{sid}").json()
    assert st_["status"] == "done", st_
    return sid


def login(a: Api, role: str = "user") -> None:
    a.user("q@x.io", role)
    a.login("q@x.io")


# ---------------------------------------------------------------- BUG-1 (high)
# Items were merged across line breaks, so two people on two lines shared one token and
# the second DOCX paragraph / table cell came out empty.


def test_bug1_two_people_on_two_docx_paragraphs_stay_apart(tmp_path: Path) -> None:
    d = docx.Document()
    d.add_paragraph("Rahul Sharma")
    d.add_paragraph("Priya Nair")
    buf = io.BytesIO()
    d.save(buf)
    with api(tmp_path, HITS) as a:
        login(a)
        sid = done_scan(a, files={"file": ("p.docx", buf.getvalue())})
        items = a.http.get(f"/api/v1/scans/{sid}/result").json()["items"]
        tokens = [i["token"] for i in items if i["pii_type"] == "PERSON"]
        assert len(tokens) == 2 and tokens[0] != tokens[1]
        out = docx.Document(io.BytesIO(a.http.get(f"/api/v1/scans/{sid}/download").content))
        assert [p.text for p in out.paragraphs] == tokens  # no paragraph emptied


def test_bug1_merged_docx_cell_keeps_its_token(tmp_path: Path) -> None:
    d = docx.Document()
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).merge(t.cell(0, 1)).text = "Rahul Sharma"
    buf = io.BytesIO()
    d.save(buf)
    with api(tmp_path, HITS) as a:
        login(a)
        sid = done_scan(a, files={"file": ("m.docx", buf.getvalue())})
        out = docx.Document(io.BytesIO(a.http.get(f"/api/v1/scans/{sid}/download").content))
        cell = out.tables[0].rows[0].cells[0].text
        assert cell.startswith("PERSON_") and "Rahul" not in cell


def test_bug1_weekday_never_joins_a_date_on_the_next_line() -> None:
    text = "Monday\n12 March 2026"
    spans = fuse(text, [Span(7, 20, "12 March 2026", PiiType.DATE, 0.99, "rules")])
    assert [s.text for s in spans] == ["12 March 2026"]


_line = st.text(alphabet=st.sampled_from(list("ab😀 é")), min_size=1, max_size=6)


@settings(max_examples=150, deadline=None)
@given(st.lists(_line, min_size=2, max_size=6), st.data())
def test_property_no_fused_item_spans_a_line_break(lines: list[str], data: st.DataObject) -> None:
    text = "\n".join(lines)
    spans = []
    pos = 0
    for ln in lines:  # one PERSON per non-blank line, as a detector would report
        if ln.strip():
            spans.append(Span(pos, pos + len(ln), ln, PiiType.PERSON, 0.95, "ner"))
        pos += len(ln) + 1
    for s in fuse(text, spans):
        assert "\n" not in text[s.start : s.end]


@settings(max_examples=150, deadline=None)
@given(st.lists(_line, min_size=1, max_size=6), st.data())
def test_property_rebuild_matches_a_naive_replay(lines: list[str], data: st.DataObject) -> None:
    """Whatever the items, the rebuilt text equals replaying them on the plain string, and
    every parsed line keeps its own text (nothing moves between lines)."""
    doc = parse_txt("\n".join(lines).encode())
    text = doc.text
    items = []
    for seg in doc.segments:  # at most one item inside each line
        if seg.end - seg.start >= 1 and data.draw(st.booleans()):
            a = data.draw(st.integers(seg.start, seg.end - 1))
            b = data.draw(st.integers(a + 1, seg.end))
            items.append(Item(len(items), 1, a, b, PiiType.PERSON, Action.REDACT, None))
    rb = rebuild(doc, items)
    expect = text
    for it in sorted(items, key=lambda i: -i.start):
        expect = expect[: it.start] + "[REDACTED]" + expect[it.end :]
    assert rb.text == expect
    assert "\n".join(rb.part_texts(len(doc.segments))) == expect


# ---------------------------------------------------------------- BUG-2 (medium)
# Empty input (CSV with only a header, blank file) failed as "file could not be read";
# PRD 12 says: "No personal data found." + still offer the download.


@pytest.mark.parametrize("raw", [b"name,phone\n", b"\n\n", b"   \n"])
def test_bug2_nothing_to_find_is_done_not_failed(tmp_path: Path, raw: bytes) -> None:
    name = "a.csv" if raw.startswith(b"name") else "a.txt"
    with api(tmp_path, HITS) as a:
        login(a)
        sid = done_scan(a, files={"file": (name, raw)})
        st_ = a.http.get(f"/api/v1/scans/{sid}").json()
        assert st_["risk"]["level"] == "LOW"
        assert a.http.get(f"/api/v1/scans/{sid}/result").json()["items"] == []
        assert a.http.get(f"/api/v1/scans/{sid}/download").content == raw
        assert a.c.saver.get_tuple({"configurable": {"thread_id": sid}}) is None


# ---------------------------------------------------------------- BUG-3 (low)


def test_bug3_pasted_text_too_long_says_so(tmp_path: Path) -> None:
    with api(tmp_path, HITS) as a:
        login(a)
        assert a.post("/api/v1/scans", data={"text": "a" * 200_000}).status_code == 202
        r = a.post("/api/v1/scans", data={"text": "a" * 200_001})
        err = r.json()["error"]
        assert r.status_code == 422 and err["field"] == "text"
        assert err["message"] == "Text is too long (max 200,000 characters)."


# ---------------------------------------------------------------- BUG-4 (low)


def test_bug4_windows_line_endings_are_kept(tmp_path: Path) -> None:
    with api(tmp_path, HITS) as a:
        login(a)
        sid = done_scan(a, files={"file": ("a.txt", b"Rahul Sharma\r\n\r\nphone 98470 12345\r\n")})
        out = a.http.get(f"/api/v1/scans/{sid}/download").content
        assert out.count(b"\r\n") == 3 and b"Rahul" not in out
        sid = done_scan(a, files={"file": ("a.csv", b"name,phone\nRahul Sharma,98470 12345\n")})
        assert b"\r" not in a.http.get(f"/api/v1/scans/{sid}/download").content


# ---------------------------------------------------------------- checked, no bug


def test_offsets_are_code_points_even_with_emoji(tmp_path: Path) -> None:
    """API contract (API 4.9): start/end count Unicode code points. Python slices match;
    JavaScript must not slice UTF-16 directly (see API.md note)."""
    text = "😀👍🏽 Rahul Sharma called 98470 12345"
    with api(tmp_path, HITS) as a:
        login(a)
        sid = done_scan(a, data={"text": text})
        r = a.http.get(f"/api/v1/scans/{sid}/result").json()
        got = {i["pii_type"]: r["original_text"][i["start"] : i["end"]] for i in r["items"]}
        assert got == {"PERSON": "Rahul Sharma", "PHONE": "98470 12345"}


def test_csv_quoted_newlines_and_extra_columns(tmp_path: Path) -> None:
    raw = b'name,note\nRahul Sharma,"line one\nline two 98470 12345",extra\n'
    with api(tmp_path, HITS) as a:
        login(a)
        sid = done_scan(a, files={"file": ("a.csv", raw)})
        out = a.http.get(f"/api/v1/scans/{sid}/download").content.decode()
        assert '"line one\nline two PHONE_' in out and out.count(",") == 3
        assert "Rahul" not in out and "98470" not in out


def test_same_person_in_two_scans_survives_deleting_one(tmp_path: Path) -> None:
    with api(tmp_path, HITS) as a:
        login(a, "admin")
        s1 = done_scan(a, data={"text": "Rahul Sharma here"})
        s2 = done_scan(a, data={"text": "Rahul Sharma again"})
        tok = a.http.get(f"/api/v1/scans/{s1}/result").json()["items"][0]["token"]
        assert a.http.get(f"/api/v1/scans/{s2}/result").json()["items"][0]["token"] == tok
        assert a.http.delete(f"/api/v1/scans/{s1}", headers={"Origin": ORIGIN}).status_code == 204
        r = a.post("/api/v1/admin/reveal", json={"token": tok, "reason": "still used by scan 2"})
        assert r.json()["value"] == "Rahul Sharma"


def test_forwarded_for_header_cannot_dodge_the_lockout(tmp_path: Path) -> None:
    with api(tmp_path, HITS) as a:
        a.user("q@x.io")
        bad = {"email": "q@x.io", "password": "wrongpass1"}
        codes = [
            a.http.post("/api/v1/auth/login", json=bad,
                        headers={"Origin": ORIGIN, "X-Forwarded-For": f"10.0.0.{i}"}).status_code
            for i in range(6)
        ]  # fmt: skip
        assert codes == [401] * 5 + [429]


def test_locked_database_answers_503_busy(tmp_path: Path) -> None:
    with api(tmp_path, HITS) as a:
        login(a)
        a.c.db.engine.dispose()

        @event.listens_for(a.c.db.engine, "connect")
        def short_wait(dbapi, rec) -> None:  # type: ignore[no-untyped-def]
            dbapi.execute("PRAGMA busy_timeout=50")

        blocker = sqlite3.connect(tmp_path / "app.db")
        blocker.execute("BEGIN IMMEDIATE")
        try:
            client = TestClient(a.http.app, raise_server_exceptions=False)  # type: ignore[arg-type]
            client.cookies = a.http.cookies
            r = client.post("/api/v1/scans", data={"text": "hello"}, headers={"Origin": ORIGIN})
        finally:
            blocker.rollback()
            blocker.close()
        assert r.status_code == 503 and r.json()["error"]["code"] == "busy"
        assert r.headers["retry-after"] == "2"
        assert a.c.files.scan_ids() == set()


def test_disk_full_on_upload_answers_503_and_stores_nothing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with api(tmp_path, HITS) as a:
        login(a)

        def full(*args: object, **kw: object) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(a.c.files, "write", full)
        r = a.post("/api/v1/scans", data={"text": "hello"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"
        assert a.http.get("/api/v1/scans").json()["items"] == []


def test_model_crash_fails_cleanly_and_retry_finishes(tmp_path: Path) -> None:
    with api(tmp_path, HITS) as a:
        login(a)
        real, calls = a.c.detectors["ner"], {"n": 0}  # type: ignore[index]

        class CrashOnce:
            def detect(self, t: str) -> list[Span]:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("model blew up")
                return real.detect(t)  # type: ignore[no-any-return]

        a.c.detectors["ner"] = CrashOnce()  # type: ignore[index]
        r = a.post("/api/v1/scans", data={"text": "Rahul Sharma called"})
        a.drain()
        sid = r.json()["id"]
        st_ = a.http.get(f"/api/v1/scans/{sid}").json()
        assert st_["status"] == "failed" and st_["error"]["code"] == "internal"
        assert "blew up" not in str(st_)  # internal details never reach the user
        assert a.post(f"/api/v1/scans/{sid}/retry").status_code == 202
        a.drain()
        assert a.http.get(f"/api/v1/scans/{sid}").json()["status"] == "done"


def test_deleting_a_paused_scan_removes_its_saved_text(tmp_path: Path) -> None:
    with api(tmp_path, [("Priya", PiiType.PERSON, 0.6)]) as a:
        login(a)
        sid = a.post("/api/v1/scans", data={"text": "Thanks Priya"}).json()["id"]
        a.drain()
        assert a.http.get(f"/api/v1/scans/{sid}").json()["status"] == "needs_review"
        assert a.http.delete(f"/api/v1/scans/{sid}", headers={"Origin": ORIGIN}).status_code == 204
        assert a.c.saver.get_tuple({"configurable": {"thread_id": sid}}) is None


def test_review_not_personal_and_retype(tmp_path: Path) -> None:
    with api(tmp_path, [("Priya", PiiType.PERSON, 0.6), ("Kochi", PiiType.LOCATION, 0.6)]) as a:
        login(a)
        sid = a.post("/api/v1/scans", data={"text": "Priya moved to Kochi"}).json()["id"]
        a.drain()
        items = a.http.get(f"/api/v1/scans/{sid}").json()["review"]["items"]
        by_text = {i["context"]["text"]: i["index"] for i in items}
        answers = [
            {"index": by_text["Priya"], "verdict": "not_pii"},
            {"index": by_text["Kochi"], "verdict": "protect", "pii_type": "ORG"},
        ]
        assert a.post(f"/api/v1/scans/{sid}/answers", json={"answers": answers}).status_code == 202
        a.drain()
        r = a.http.get(f"/api/v1/scans/{sid}/result").json()
        cleaned = "".join(s["text"] for s in r["cleaned_segments"])
        assert cleaned.startswith("Priya moved to ORG_") and "Kochi" not in cleaned


def test_general_limit_applies_to_finished_scans(tmp_path: Path) -> None:
    with api(tmp_path, HITS) as a:
        login(a)
        sid = done_scan(a, data={"text": "hello"})
        codes = [a.http.get(f"/api/v1/scans/{sid}").status_code for _ in range(121)]
        # 120 per minute per session; the upload and the first status check used 2
        assert codes[:118] == [200] * 118 and set(codes[118:]) == {429}


@pytest.mark.parametrize(
    ("name", "stored"),
    [
        ("../../etc/passwd.txt", "passwd.txt"),
        ("NOTES.TXT", "NOTES.TXT"),
        ("x" * 300 + ".txt", "x" * 251 + ".txt"),
    ],  # fmt: skip
)
def test_filenames_are_cleaned(tmp_path: Path, name: str, stored: str) -> None:
    with api(tmp_path, HITS) as a:
        login(a)
        sid = a.post("/api/v1/scans", files={"file": (name, b"hello")}).json()["id"]
        assert a.http.get(f"/api/v1/scans/{sid}").json()["filename"] == stored


@pytest.mark.parametrize("name", ["a‮txt.exe", ".txt", "noext"])
def test_tricky_extensions_are_refused(tmp_path: Path, name: str) -> None:
    with api(tmp_path, HITS) as a:
        login(a)
        r = a.post("/api/v1/scans", files={"file": (name, b"hello")})
        assert r.status_code == 415

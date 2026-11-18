"""Scan journeys through the HTTP API with a fake NER (IMPLEMENTATION_PLAN J1-J3)."""

import io
import logging
from pathlib import Path

import docx
import pytest

from app.detectors.types import PiiType
from tests.api_helpers import Api, api

TEXT = "Patient: Rahul Sharma, phone 98470 12345, email rahul@example.com."


def start(a: Api, **files: object):  # type: ignore[no-untyped-def]
    r = a.post("/api/v1/scans", **files)
    assert r.status_code == 202, r.text
    return r.json()["id"]


def test_j1_text_scan_to_result_and_download(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        a.login("a@x.io")
        sid = start(a, data={"text": TEXT})
        st = a.http.get(f"/api/v1/scans/{sid}").json()
        assert st["status"] == "queued" and st["review"] is None
        a.drain()
        st = a.http.get(f"/api/v1/scans/{sid}").json()
        assert st["status"] == "done" and st["step"] == 5 and st["risk"]["level"]

        res = a.http.get(f"/api/v1/scans/{sid}/result").json()
        cleaned = "".join(s["text"] for s in res["cleaned_segments"])
        assert res["original_text"] == TEXT.strip()
        for v in ("Rahul Sharma", "98470 12345", "rahul@example.com"):
            assert v not in cleaned
        person = next(i for i in res["items"] if i["pii_type"] == "PERSON")
        assert person["action"] == "pseudonymize" and person["output"] == person["token"]
        assert person["token"] in cleaned

        d = a.http.get(f"/api/v1/scans/{sid}/download?kind=cleaned")
        assert d.text == cleaned
        assert d.headers["content-disposition"].startswith('attachment; filename="cleaned-')
        rep = a.http.get(f"/api/v1/scans/{sid}/download?kind=report")
        assert "Rahul" not in rep.text and rep.json()["counts"]
        assert a.http.get(f"/api/v1/scans/{sid}/download?kind=x").status_code == 422

        audit = a.c.crypto.audit.store.all()
        assert [r.event for r in audit][-1] == "scan_completed"
        assert "Rahul" not in str([r.payload for r in audit])
        # checkpoint gone after commit (it held document text)
        assert a.c.saver.get_tuple({"configurable": {"thread_id": sid}}) is None


def test_j2_review_pause_answers_and_resume(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        a.login("a@x.io")
        sid = start(a, data={"text": "Please thank Priya for the files."})
        a.drain()
        st = a.http.get(f"/api/v1/scans/{sid}").json()
        assert st["status"] == "needs_review"
        item = st["review"]["items"][0]
        assert item["context"]["text"] == "Priya" and item["family"] == "identity"
        bad = a.post(
            f"/api/v1/scans/{sid}/answers",
            json={"answers": [{"index": item["index"] + 5, "verdict": "protect"}]},
        )
        assert bad.json()["error"]["code"] == "invalid_answers"
        ok = a.post(
            f"/api/v1/scans/{sid}/answers",
            json={"answers": [{"index": item["index"], "verdict": "protect"}]},
        )
        assert ok.status_code == 202
        again = a.post(
            f"/api/v1/scans/{sid}/answers",
            json={"answers": [{"index": item["index"], "verdict": "protect"}]},
        )
        assert again.json()["error"]["code"] == "not_waiting_for_review"
        a.drain()
        res = a.http.get(f"/api/v1/scans/{sid}/result").json()
        assert "Priya" not in "".join(s["text"] for s in res["cleaned_segments"])
        assert any(r.event == "review" for r in a.c.crypto.audit.store.all())


def test_restart_while_paused_asks_again(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        a.login("a@x.io")
        sid = start(a, data={"text": "Thanks Priya."})
        a.drain()
        a.c.enqueue(sid)  # as after a restart: job without answers, scan was queued
        from app.storage.worker_repo import WorkerRepo

        WorkerRepo(a.c.db).set_state(sid, "queued", "2026-11-19T10:00:00.000Z")
        a.drain()
        assert a.http.get(f"/api/v1/scans/{sid}").json()["status"] == "needs_review"


def test_docx_and_csv_uploads(tmp_path: Path) -> None:
    d = docx.Document()
    d.add_paragraph("Patient: Rahul Sharma")
    buf = io.BytesIO()
    d.save(buf)
    with api(tmp_path) as a:
        a.user("a@x.io")
        a.login("a@x.io")
        sid = start(a, files={"file": ("note.docx", buf.getvalue())})
        sid2 = start(a, files={"file": ("p.csv", b"name,phone\nRahul Sharma,98470 12345\n")})
        a.drain()
        out = a.http.get(f"/api/v1/scans/{sid}/download")
        assert out.headers["content-type"].startswith("application/vnd.openxml")
        assert "Rahul" not in docx.Document(io.BytesIO(out.content)).paragraphs[0].text
        csv_out = a.http.get(f"/api/v1/scans/{sid2}/download").text
        assert csv_out.startswith("name,phone") and "Rahul" not in csv_out


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({"file": ("a.exe", b"MZ")}, "unsupported_type"),
        ({"file": ("a.pdf", b"not a pdf")}, "unsupported_type"),
        ({"file": ("a.docx", b"PK\x03\x04broken")}, "file_unreadable"),
        ({"file": ("a.txt", b"\x00\x01\x02")}, "unsupported_type"),
        ({"data": {"text": "   "}}, "empty_input"),
        ({}, "empty_input"),
    ],
)
def test_upload_rejections(tmp_path: Path, files: dict[str, object], code: str) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        a.login("a@x.io")
        kw = (
            files.get("data")
            and {"data": files["data"]}
            or ({"files": {"file": files["file"]}} if "file" in files else {"data": {}})
        )
        r = a.post("/api/v1/scans", **kw)
        assert r.json()["error"]["code"] == code


def test_too_large_and_open_limit(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        a.login("a@x.io")
        big = b"a" * (10 * 1024 * 1024 + 1)
        r = a.post("/api/v1/scans", files={"file": ("a.txt", big)})
        assert r.status_code == 413
        for _ in range(3):
            start(a, data={"text": "hello"})
        r = a.post("/api/v1/scans", data={"text": "hello"})
        assert r.status_code == 429 and "retry-after" in r.headers


def test_pdf_without_text_fails_cleanly_and_retry(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(100, 100)
    buf = io.BytesIO()
    w.write(buf)
    with api(tmp_path) as a:
        a.user("a@x.io")
        a.login("a@x.io")
        sid = start(a, files={"file": ("scan.pdf", buf.getvalue())})
        assert a.post(f"/api/v1/scans/{sid}/retry").json()["error"]["code"] == "scan_not_failed"
        a.drain()
        st = a.http.get(f"/api/v1/scans/{sid}").json()
        assert st["status"] == "failed" and st["error"]["code"] == "pdf_no_text"
        assert st["error"]["step"] == 1
        assert a.http.get(f"/api/v1/scans/{sid}/result").json()["error"]["code"] == "scan_not_done"
        assert a.post(f"/api/v1/scans/{sid}/retry").status_code == 202


def test_owner_scoping_everywhere(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        a.user("b@x.io")
        a.login("a@x.io")
        sid = start(a, data={"text": TEXT})
        a.drain()
        a.login("b@x.io")
        assert a.http.get("/api/v1/scans").json()["items"] == []
        for path in ("", "/result", "/download"):
            assert a.http.get(f"/api/v1/scans/{sid}{path}").status_code == 404
        assert a.post(f"/api/v1/scans/{sid}/retry").status_code == 404
        assert (
            a.post(
                f"/api/v1/scans/{sid}/answers", json={"answers": [{"index": 0, "verdict": "keep"}]}
            ).status_code
            == 404
        )
        assert (
            a.http.delete(
                f"/api/v1/scans/{sid}", headers={"Origin": "http://localhost:8000"}
            ).status_code
            == 404
        )
        assert a.http.get("/api/v1/scans/not-a-uuid").status_code == 404


def test_list_paging_and_delete(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        a.login("a@x.io")
        ids = []
        for _ in range(3):
            ids.append(start(a, data={"text": TEXT}))
            a.drain()
        p1 = a.http.get("/api/v1/scans?limit=2").json()
        assert [i["id"] for i in p1["items"]] == ids[::-1][:2] and p1["next_cursor"]
        p2 = a.http.get(f"/api/v1/scans?limit=2&cursor={p1['next_cursor']}").json()
        assert [i["id"] for i in p2["items"]] == [ids[0]] and p2["next_cursor"] is None
        assert a.http.get("/api/v1/scans?cursor=garbage!").status_code == 422
        h = {"Origin": "http://localhost:8000"}
        assert a.http.delete(f"/api/v1/scans/{ids[0]}", headers=h).status_code == 204
        assert a.http.delete(f"/api/v1/scans/{ids[0]}", headers=h).status_code == 404
        assert ids[0] not in a.c.files.scan_ids()


def test_logs_never_hold_document_text(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    with api(tmp_path, hits=[("Rahul Sharma", PiiType.PERSON, 0.95)]) as a:
        a.user("a@x.io")
        a.login("a@x.io")
        sid = start(a, files={"file": ("Rahul_Sharma_notes.txt", TEXT.encode())})
        a.drain()
        a.http.get(f"/api/v1/scans/{sid}/result")
    logged = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    for secret in ("Rahul", "98470", "rahul@example.com"):
        assert secret not in logged

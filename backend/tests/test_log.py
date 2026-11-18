import json
import logging

from app.log import JsonFormatter


def test_only_allowed_fields_are_logged() -> None:
    rec = logging.LogRecord("app", logging.INFO, __file__, 1, "scan finished", None, None)
    rec.scan_id = "3f2a9c1e"
    rec.text = "Patient Arjun Nair, 98470 12345"  # must never reach the log
    rec.filename_value = "resume_rahul.pdf"
    out = JsonFormatter().format(rec)
    data = json.loads(out)
    assert data["msg"] == "scan finished" and data["scan_id"] == "3f2a9c1e"
    assert "Arjun" not in out and "98470" not in out and "rahul" not in out


def test_exceptions_log_type_only() -> None:
    try:
        raise ValueError("Arjun Nair 98470 12345")
    except ValueError:
        import sys

        rec = logging.LogRecord("app", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    out = JsonFormatter().format(rec)
    assert "ValueError" in out and "Arjun" not in out

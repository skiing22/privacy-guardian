"""Structured JSON logging (ARCHITECTURE 13.3, NFR-04).

Only allow-listed context fields are written. Anything else passed via `extra=` is
dropped, so a value from a document can never reach the logs by accident. Messages are
fixed developer strings: never format document text, values or filenames into them.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

ALLOWED_FIELDS = frozenset(
    {"request_id", "user_id", "scan_id", "route", "method", "status", "duration_ms",
     "error_code", "event", "step", "round", "count"}
)  # fmt: skip


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k in ALLOWED_FIELDS:
            if k in record.__dict__:
                out[k] = record.__dict__[k]
        if record.exc_info and record.exc_info[0] is not None:
            out["exc_type"] = record.exc_info[0].__name__  # type only: no message, no locals
        return json.dumps(out, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):  # same JSON format for the server
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True

"""Starts the REAL app (FastAPI + SQLite + worker + built frontend) for the browser tests,
with one change: the model is replaced by a fixed name finder, so the same text always
pauses for the same review. The container image is checked separately (scripts/smoke.sh).

    python e2e/server.py <data_dir>      # port 8000; ADMIN_EMAIL/ADMIN_PASSWORD from env

Use a new, empty data folder for every run: J4 tampers with the audit log on purpose.
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn  # noqa: E402
from app.config import Settings  # noqa: E402
from app.detectors.context import ContextDetector  # noqa: E402
from app.detectors.rules import RuleDetector  # noqa: E402
from app.detectors.types import PiiType, Span  # noqa: E402
from app.main import create_app  # noqa: E402

# Phrase -> (type, score). 0.95 is sure; 0.6 is unsure, so it goes to review.
FIXED = {
    "Rahul Sharma": (PiiType.PERSON, 0.95),
    "Priya": (PiiType.PERSON, 0.6),
    "Nehru Nagar": (PiiType.ADDRESS, 0.58),
}


class FixedNer:
    def detect(self, text: str) -> list[Span]:
        out = []
        for phrase, (t, score) in FIXED.items():
            for m in re.finditer(re.escape(phrase), text):
                out.append(Span(m.start(), m.end(), phrase, t, score, "ner"))
        return out


def main() -> None:
    data = Path(sys.argv[1])
    s = Settings(
        data_dir=data,
        static_dir=ROOT / "frontend" / "dist",
        admin_email=os.environ["ADMIN_EMAIL"],
        admin_password=os.environ["ADMIN_PASSWORD"],
    )
    detectors = {"rules": RuleDetector(), "ner": FixedNer(), "context": ContextDetector()}
    uvicorn.run(
        create_app(s, detectors=detectors), host="127.0.0.1", port=8000, log_level="warning"
    )


if __name__ == "__main__":
    main()

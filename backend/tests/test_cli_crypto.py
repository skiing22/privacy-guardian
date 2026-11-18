"""End-to-end CLI crypto demo: scan -> anchor -> reidentify -> tamper -> verify fails."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app import cli
from app.detectors.types import PiiType, Span


class FakeNer:
    def detect(self, text: str) -> list[Span]:
        return [
            Span(m.start(), m.end(), m.group(), PiiType.PERSON, 0.95, "ner")
            for m in re.finditer("Arjun Nair", text)
        ]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for k in ("PG_TOKEN_KEY", "PG_AUDIT_KEY", "PG_VAULT_KEY"):
        monkeypatch.delenv(k, raising=False)  # use DEV keys
    monkeypatch.setattr(cli, "default_detectors", lambda _m: {"ner": FakeNer()})
    return tmp_path


def run(*args: str) -> int:
    return cli.main(list(args))


def test_full_crypto_demo(env: Path, capsys: Any) -> None:
    note = env / "n.txt"
    note.write_text("Patient Arjun Nair called.")
    d = ["--data", str(env)]

    assert run("scan", str(note), "--auto", *d, "--beliefs", str(env / "b.json")) == 0
    out = capsys.readouterr().out
    token = re.search(r"PERSON_[0-9a-f]{6}", out)
    assert token, out

    anchor = ["--anchor-file", str(env / "a.json")]
    assert run("audit", "anchor", *d, *anchor) == 0
    assert run("audit", "verify", *d, *anchor) == 0

    assert run("reidentify", token.group(), "--reason", "short", *d) == 1  # reason too short
    assert run("reidentify", token.group(), "--reason", "court order 2026/77", *d) == 0
    assert "Arjun Nair" in capsys.readouterr().out
    assert run("audit", "verify", *d, *anchor) == 0  # appending after the anchor is fine

    # tamper: change the recorded risk in line 1 by hand
    log = env / "audit.jsonl"
    lines = log.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["payload"]["risk"] = "HIGH"
    lines[0] = json.dumps(rec)
    log.write_text("\n".join(lines) + "\n")
    assert run("audit", "verify", *d, *anchor) == 2
    assert "TAMPERED at record #0" in capsys.readouterr().out
    assert "Arjun" not in log.read_text()  # never raw PII in the log

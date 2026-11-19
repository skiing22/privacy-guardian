import io
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import app.services.auth as auth
from app.config import get_settings
from app.manage import main


@pytest.fixture
def data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    auth.BCRYPT_ROUNDS = 4
    yield tmp_path
    get_settings.cache_clear()


def test_manage_commands(data: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["migrate"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO("long-enough-pw\n"))
    assert main(["create-user", "a@x.io", "--role", "admin", "--password-stdin"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO("long-enough-pw\n"))
    assert main(["create-user", "a@x.io", "--password-stdin"]) == 1  # duplicate
    assert main(["disable-user", "a@x.io"]) == 0
    assert main(["retention"]) == 0
    assert main(["audit-verify"]) == 0
    assert main(["backup", str(data / "bk")]) == 0
    with closing(sqlite3.connect(data / "bk" / "app.db")) as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    assert "long-enough-pw" not in capsys.readouterr().out


def test_restore_from_backup(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DATABASE 10.4: copy a backup into an empty DATA_DIR, start, verify the audit chain."""
    import shutil

    monkeypatch.setattr("sys.stdin", io.StringIO("long-enough-pw\n"))
    assert main(["create-user", "a@x.io", "--password-stdin"]) == 0
    assert main(["backup", str(data / "bk")]) == 0
    restored = data / "restored"
    shutil.copytree(data / "bk", restored)
    monkeypatch.setenv("DATA_DIR", str(restored))
    get_settings.cache_clear()
    assert main(["audit-verify"]) == 0
    with closing(sqlite3.connect(restored / "app.db")) as db:
        assert db.execute("SELECT count(*) FROM audit_log").fetchone()[0] == 1  # user_created

"""Server admin commands (run inside the container, DATABASE 10):

    python -m app.manage migrate                      # upgrade the database (backs up first)
    python -m app.manage create-user a@x.io --role admin   # asks for the password
    echo "$PW" | python -m app.manage create-user a@x.io --password-stdin
    python -m app.manage disable-user a@x.io
    python -m app.manage backup /backups/2026-11-19   # app.db + files/ + checkpoints.db
    python -m app.manage retention                    # run the retention job once
    python -m app.manage audit-verify                 # chain vs anchor file; exit 2 if bad

Passwords never go on the command line (shell history, process list).
"""

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

from app.config import get_settings, load_keyring
from app.services.container import Container
from app.services.errors import AppError
from app.services.retention import run_retention
from app.storage.db import copy_files, migrate


def _container() -> Container:
    s = get_settings()
    ring, dev = load_keyring(s)
    if dev:
        print("! using DEV keys (no PG_*_KEY set)", file=sys.stderr)
    migrate(s.data_dir)
    return Container.build(s, ring)


def _password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    pw = getpass.getpass("Password (8-128 chars): ")
    if pw != getpass.getpass("Repeat password: "):
        raise SystemExit("passwords differ")
    return pw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.manage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    cu = sub.add_parser("create-user")
    cu.add_argument("email")
    cu.add_argument("--role", choices=["user", "admin"], default="user")
    cu.add_argument("--password-stdin", action="store_true")
    du = sub.add_parser("disable-user")
    du.add_argument("email")
    bk = sub.add_parser("backup")
    bk.add_argument("dest")
    sub.add_parser("retention")
    sub.add_parser("audit-verify")
    args = ap.parse_args(argv)

    if args.cmd == "migrate":
        migrate(get_settings().data_dir)
        print("database is up to date")
        return 0

    c = _container()
    try:
        if args.cmd == "create-user":
            uid = c.auth.create_user(args.email, _password(args.password_stdin), args.role)
            print(f"created user {uid} ({args.role})")
        elif args.cmd == "disable-user":
            c.auth.disable_user(args.email)
            print("user disabled; their sessions ended")
        elif args.cmd == "backup":
            dest = Path(args.dest)
            c.db.backup_to(dest / "app.db")
            src = sqlite3.connect(c.settings.data_dir / "checkpoints.db")
            dst = sqlite3.connect(dest / "checkpoints.db")
            src.backup(dst)
            src.close()
            dst.close()
            copy_files(c.settings.data_dir / "files", dest / "files")
            print(f"backup written to {dest} (keep audit.anchor.json somewhere else)")
        elif args.cmd == "retention":
            print(run_retention(c))
        elif args.cmd == "audit-verify":
            saved = c.load_anchor()
            res = c.crypto.audit.verify(saved[0] if saved else None)
            if not res.ok:
                print(f"TAMPERED at #{res.first_bad_seq}: {res.reason}")
                return 2
            print(f"OK: {res.checked} records" + (f", anchor seq {saved[0].seq}" if saved else ""))
    except AppError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return 1
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

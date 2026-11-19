# ADR-0023: Backend implementation choices (step 10, P2 to P10)

- Status: proposed (needs approval)
- Date: 2026-11-19

## Context

Implementing DATABASE.md, API.md and ARCHITECTURE.md raised a few choices the docs did not
fix. They are recorded here; none changes the approved schema.

## Decisions

1. **Schema as SQL, data access with SQLAlchemy Core.** Migration `0001` runs the exact
   `CREATE TABLE ... STRICT` statements of DATABASE.md 3 (from `storage/schema_sql.py`)
   instead of ORM models (plan P2.2 said models). STRICT tables, table CHECKs and triggers
   are SQLite features the ORM cannot express cleanly; raw DDL keeps them exact. Queries use
   `text()` with bound parameters only. Repositories return frozen dataclasses.
2. **Plain checkpoints refused.** LangGraph's `EncryptedSerializer` loads an unencrypted
   row as is. We subclass it to refuse such rows, so a row planted on disk cannot be loaded.
3. **Audit lock order.** `AuditLog.append` takes the database write lock first (via the
   store's `atomic()`), then its thread lock. One order everywhere, so threads never wait
   on each other in a cycle.
4. **Tokens kept per round.** `RoundRecord` gained `tokens` (default empty, so older
   checkpoints still load). The decisions table needs the token of every pseudonymized item.
5. **Cleaned output is rebuilt, not stored twice.** The result view and the writers replay
   the stored decisions on the parsed original (DATABASE 2.1). The worker checks the
   rebuilt text equals the graph's output before saving; a mismatch fails the scan.
6. **DOCX headers and footers are emptied in the cleaned file.** The parser does not scan
   them, so they could hold names or ids. Emptying is the safe default; scanning them is a
   later feature. *Needs approval.*
7. **Scan delete and the vault.** Delete removes vault rows only the deleted scan used,
   unless another scan is running at that moment (it may have stored rows it has not
   referenced yet); then retention removes them later.
8. **Health.** `503` while the model loads (API 4.1), body
   `{status: "starting", model_ready: false, version, error}`. Docker `start-period` is
   120 s to allow for model loading.
9. **Dev without a model.** In `ENV=dev`, if `NER_MODEL_PATH` does not exist, the app runs
   rules and context only and logs a warning. In `prod` the app stays not ready instead.
10. **Server commands** live in `python -m app.manage` (migrate, create-user,
    disable-user, backup, retention, audit-verify). Passwords are read from a prompt or
    stdin, never from arguments.
11. **Passwords.** bcrypt (cost 12) over base64(SHA-256(password)), so all 128 allowed
    characters count (bcrypt reads only 72 bytes).
12. **Answers lost on restart.** Review answers travel in the in-memory queue. If the
    process restarts before the worker uses them, the scan goes back to `needs_review` and
    the user answers again.

## Consequences

- New runtime dependencies: `sqlalchemy`, `alembic`, `langgraph-checkpoint-sqlite`,
  `bcrypt`, `python-multipart` (FastAPI needs it for uploads).
- Retention runs at startup and every 24 hours.

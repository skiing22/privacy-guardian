# Privacy Guardian Agent v2

Finds personal data (PII) in text and files, decides what to do with each item, and returns a safe copy
with a tamper-evident audit log. Built on a LangGraph agent graph with parallel detectors, a human
review pause, a leak-check loop, and learned sensitivity beliefs.

## Status
M0 - project setup. See `docs/SRS.md` and `docs/decisions/`.

## Run locally
```bash
cp .env.example .env
docker compose up --build
curl localhost:8000/api/v1/health
```

## Dev without Docker
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest && ruff check . && mypy app
uvicorn app.main:app --reload
```

## Repo rules
- `main` is always deployable; work on `feature/<name>` branches and merge by PR.
- Conventional Commits, with requirement IDs: `feat(graph): add verifier loop (FR-21)`.
- Every real design choice gets an ADR in `docs/decisions/`.

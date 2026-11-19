# Privacy Guardian Agent v2

Finds personal data in text and files, decides what to do with each item, and returns a safe copy
with a tamper-evident audit log. Built on a LangGraph agent graph with parallel detectors, a human
review pause, a leak-check loop, and learned sensitivity beliefs.

## Status
Backend core (M0 to M4) done, tag `v0.5.0`. Web backend (database, auth, scan and admin API,
worker, retention) done (P2 to P10). Web app in progress: see
[`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md).

## Documents
| | |
| --- | --- |
| [PRD](docs/PRD.md) | What we build and why |
| [DESIGN](docs/DESIGN.md) | How it looks and reads |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | How it is built |
| [DATABASE](docs/DATABASE.md) | Data model |
| [API](docs/API.md) | API contract |
| [AGENTS](AGENTS.md) | Rules for every change |
| [Decisions](docs/decisions/) | Why each choice was made (ADRs) |

## Run with Docker
```bash
cp .env.example .env          # optional in dev
mkdir .secrets && echo hf_your_read_only_token > .secrets/hf_token   # never commit
# set MODEL_REPO, MODEL_REVISION, MODEL_SHA256 in .env (docs/API.md 8.2), then:
docker compose up --build
# no access to the model yet? try the app with a random model:
#   MODEL_SOURCE=fake docker compose up --build   (.secrets/hf_token may be empty)
# open http://localhost:8000      health: http://localhost:8000/health
```

**Model setup, once (P11.1):** create a private Hugging Face model repo, upload the
`ner-distilbert-v1` folder (safetensors weights), note the commit hash, and run
`python backend/scripts/model_fetch.py hash ml/models/ner-distilbert-v1` for `MODEL_SHA256`.
For CI on `main`, add secret `HF_TOKEN` and variables `MODEL_REPO`, `MODEL_REVISION`,
`MODEL_SHA256` in the repo settings.

## Develop without Docker
Two terminals. Windows: use `.venv\Scripts\activate` instead of `source .venv/bin/activate`.

**Backend** (http://127.0.0.1:8000)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # add ",ml" for the real NER model: ".[dev,ml]"
uvicorn app.main:app --reload
```

**Frontend** (http://localhost:5173, proxies `/api` and `/health` to the backend)
```bash
cd frontend
npm ci
npm run dev
```

## Checks (CI runs all of these; all must pass before merge)
```bash
# backend/
ruff check . && ruff format --check . && mypy app && python scripts/check_layers.py && pytest --cov=app
# frontend/
npm run format:check && npm run typecheck && npm run lint && npm test && npm run build
npm run gen:api                     # after any API change; commit src/api/schema.d.ts
```

## Server commands
```bash
cd backend                          # in Docker: docker compose exec app python -m app.manage ...
python -m app.manage create-user you@example.com --role admin   # asks for the password
python -m app.manage backup ../backups/today                    # see docs/runbooks/backup-restore.md
python -m app.manage audit-verify
```
Or set `ADMIN_EMAIL` and `ADMIN_PASSWORD` once: the first admin is created at first start.

## CLI demo (real model, no web app needed)
```bash
cd backend
python -m app.cli scan ../data/samples/patient_note.txt
python -m app.cli audit verify
```

## Repo rules
See [AGENTS.md](AGENTS.md). In short: branch per change, Conventional Commits with requirement ids
(`feat(graph): verifier loop (FR-21)`), green CI before merge, an ADR for every real decision.

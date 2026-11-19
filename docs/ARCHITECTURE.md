# ARCHITECTURE: Privacy Guardian Agent v2

> How the product in **PRD.md** and **DESIGN.md** is built. Where this file and the older SRS disagree, this file wins. Decisions D13 to D17 are in section 18 (approved, ADR-0022); everything else follows PRD decisions D1 to D12 (ADR-0021).
>
> **Status column** below: ✅ exists on `main` (tag `v0.5.0`) · ⬜ to build.

---

## 0. Summary

**One container, one process, one database file.**

- A **FastAPI** app serves both the JSON API and the built **React** frontend from the same origin.
- Scans run on **one background worker thread** inside the same process, using the existing **LangGraph** agent graph and the **NER model loaded once** at startup.
- **SQLite** holds app data; a second SQLite file holds LangGraph checkpoints; uploaded files are **encrypted** on disk.
- All three live in **one data folder**, which is the only thing that must survive a restart.
- **No runtime calls to outside services.** Documents never leave the server.

### Principles

1. **Simplest thing that meets the PRD.** No message queue, no cache server, no microservices, no Kubernetes.
2. **The domain code stays pure.** Detection, fusion, policy, graph and crypto (already built and tested) do not know about HTTP or the database. They talk to storage through the small interfaces they already define.
3. **Raw personal data lives in as few places as possible**, encrypted where it rests, and deleted on a schedule.
4. **Every scale step is a swap, not a rewrite.** SQLite → Postgres, thread → worker process, one container → two, each without touching domain code (section 17).

---

## 1. Tech stack

### 1.1 MVP stack

| Layer | Choice | Why | Status |
| --- | --- | --- | --- |
| Language (backend) | Python 3.11 | ML, LangGraph and the existing 125 tests are Python | ✅ |
| Web framework | FastAPI + Pydantic v2 | Typed requests/responses, automatic OpenAPI docs, already in repo | ✅ (health only) |
| Agent workflow | LangGraph 1.x | Parallel detectors, review interrupt, verifier loop, checkpoints (ADR-0001, 0018) | ✅ |
| NER | Hugging Face Transformers + PyTorch (CPU wheel), our DistilBERT | Already trained and evaluated (ADR-0011) | ✅ |
| Parsing | pypdf, python-docx, stdlib csv | Pure Python, no system packages (ADR-0019) | ✅ |
| Crypto | `cryptography` (AES-GCM), stdlib `hmac`/`hashlib` | Audited library, no custom primitives (ADR-0020) | ✅ |
| Database | SQLite (WAL mode) via SQLAlchemy 2.x | One file, no server to run (D2); SQLAlchemy keeps a later Postgres move small | ⬜ |
| Migrations | Alembic | Standard with SQLAlchemy; schema changes are versioned and tested | ⬜ |
| Graph checkpoints | `langgraph-checkpoint-sqlite` (SqliteSaver) | Official saver; accepts our allow-list serializer | ⬜ |
| Passwords | `bcrypt` | Slow hash made for passwords | ⬜ |
| Frontend | React 18 + TypeScript + Vite | D5; Vite gives a fast build to static files | ⬜ |
| Routing | React Router | Real, shareable URLs (DESIGN 6) | ⬜ |
| Server state | TanStack Query | Built-in polling, retries and caching; replaces hand-written fetch state (D6) | ⬜ |
| Styling | Tailwind CSS with DESIGN.md tokens | DESIGN.md is written in Tailwind steps; tokens become the Tailwind theme | ⬜ |
| Icons, fonts | Phosphor (React), Manrope + Geist Mono self-hosted via Fontsource | DESIGN.md 3 and 5.9; self-hosting keeps a strict CSP and no third-party font calls | ⬜ |
| Backend tests | pytest, Hypothesis, httpx TestClient | Already in use | ✅ |
| Frontend tests | Vitest (logic), Playwright (3 end-to-end journeys) | Small, standard | ⬜ |
| Lint / types | ruff, mypy strict; ESLint + `tsc --noEmit` | ruff/mypy already gate CI | ✅ / ⬜ |
| Packaging | One multi-stage Dockerfile | One artifact to run anywhere | 🟡 backend only |
| CI | GitHub Actions, required checks on `main` | Already enforced by branch rule | ✅ |

### 1.2 Considered and not used (MVP)

| Not used | Why not |
| --- | --- |
| PostgreSQL | A server to run and pay for; one user at a time does not need it (D2). Kept as the first scale step |
| Celery / Redis / RQ | A second and third service just to run one scan at a time; a worker thread is enough |
| Server-Sent Events / WebSockets | Polling every 1 s is enough for ~1 s scans (D6) |
| JWT | Cannot be revoked without extra machinery; server-side sessions are simpler for one origin (D14) |
| Next.js / server rendering | No SEO need inside the app; static React files served by FastAPI are simpler |
| Redux / Zustand | Server state is in TanStack Query; the rest is local component state |
| A component library (MUI, shadcn) | DESIGN.md defines its own small set; a library would fight the tokens |
| External LLM API | Out of scope; would send personal data off the server |

---

## 2. System overview

```
 Browser (React SPA)
   │  HTTPS, same origin, session cookie
   ▼
┌───────────────────────────── one container ─────────────────────────────┐
│ FastAPI app                                                              │
│  ├─ /api/v1/*  → routes → services ─────────────┐                        │
│  └─ /*         → built frontend (static files)  │                        │
│                                                 ▼                        │
│  Scan worker (1 thread, FIFO queue)  ──►  LangGraph agent graph          │
│                                           ├─ detectors: rules │ NER │ context (parallel)
│                                           ├─ fuse → review (interrupt) → policy → verify ⟲
│                                           └─ crypto: HMAC tokens, vault, audit log
│  NER model: loaded once at startup, shared read-only                     │
│  Daily cleanup thread (retention)                                        │
└───────────────┬──────────────────────────────────────────────────────────┘
                │ local disk only
                ▼
 /data  (the only persistent volume)
   ├─ app.db           SQLite: users, sessions, scans, decisions, beliefs, rules, vault, tokens, audit
   ├─ checkpoints.db   SQLite: LangGraph checkpoints (encrypted)
   └─ files/           uploaded originals and cleaned outputs (encrypted)

 Secrets: 4 keys + admin bootstrap in environment variables (never on disk, never in git)
```

---

## 3. Backend architecture

### 3.1 Layers

| Layer | Folder | May import | Holds |
| --- | --- | --- | --- |
| **API** | `app/api/` | services, schemas | Routes, request/response schemas, auth dependencies, error mapping. No business logic |
| **Services** | `app/services/` | domain, storage | Use cases: start scan, submit answers, build download, reveal value, verify audit, cleanup. Transactions start and end here |
| **Domain** (exists) | `app/detectors`, `fusion`, `policy`, `graph`, `crypto`, `parsers` | each other only | All detection, decision, graph and crypto logic. Pure, unit-tested |
| **Storage** | `app/storage/` | domain interfaces | SQLAlchemy models, repositories, SQLite implementations of the domain's store interfaces, encrypted file store |
| **Runtime** | `app/runtime/` | services | Startup/shutdown (model load, worker, cleanup thread), the scan worker |

**Rule:** domain never imports `api`, `services` or `storage`. CI enforces it with an import check.

### 3.2 Store interfaces (already defined by the domain)

The domain already talks to storage through small interfaces. M5 adds SQLite implementations; the in-memory and JSON-file versions stay for tests and the CLI.

| Interface | Methods | Today | M5 |
| --- | --- | --- | --- |
| `BeliefStore` | get, put | in-memory, JSON file | `SqlBeliefStore` |
| `TokenRegistry` | get, put | in-memory, JSON file | `SqlTokenRegistry` |
| `VaultStore` | get, put | in-memory, JSON file | `SqlVaultStore` (+ delete by scan) |
| `AuditStore` | append, all | in-memory, JSONL file | `SqlAuditStore` (append-only) |
| Graph checkpointer | LangGraph saver | in-memory | `SqliteSaver` with encrypted serializer |

### 3.3 Scan worker

- **One worker thread**, a FIFO queue in memory, scan state in the database. One scan runs at a time: the model is CPU-bound, so parallel scans would only slow each other down.
- The API never runs a scan inside a request. It saves the upload, creates the scan row (`queued`), enqueues the id, and returns at once.
- The worker runs the graph with `thread_id = scan id`. After each node it writes the current step and round to the scan row (this is what polling reads).
- At the review interrupt the worker sets `needs_review` and moves on to the next scan. Submitting answers enqueues the scan again; the worker resumes it from the checkpoint.
- **Startup recovery:** scans left `running` or `queued` by a crash are put back in the queue and resume from their last checkpoint (FR-23).

### 3.4 Scan states

```
queued ──► running ──► needs_review ──(answers)──► queued ──► running ──► done
              │                                                  │
              └──────────────► failed ◄──────────────────────────┘
deleted (by user or retention) from any final state
```

---

## 4. Frontend architecture

| Concern | Approach |
| --- | --- |
| Shape | Single-page app, built to static files, served by FastAPI from `/` |
| Routes | `/login`, `/scans`, `/scans/new`, `/scans/:id`, `/admin/rules`, `/admin/audit`, `/privacy`, `*` (404); `/` = landing S0 when built (M7), else redirect to `/scans` |
| Server data | TanStack Query: one hook per API resource; scan detail polls every 1 s **only** while status is `queued` or `running`, and stops otherwise |
| Local state | Component state for UI (selected item, view mode, review answers before submit) |
| Auth state | `GET /api/v1/auth/me` on load; a 401 anywhere sends the user to `/login?next=…` |
| Design system | Tailwind theme built from DESIGN.md tokens; one `ui/` folder holding only the components in DESIGN.md section 5 |
| Document rendering | The sheet renders the text with marks from item offsets (start, end). The cleaned view is rendered from decisions, not from a second copy of the text, so marks and results always line up |
| Keyboard | One keyboard handler per page (S4), disabled while focus is in an input (DESIGN 9) |
| Accessibility | Semantic HTML first; live regions for progress and review (DESIGN 11) |
| Performance | Route-level code splitting; no runtime CSS-in-JS; fonts subset to Latin |

### 4.1 Frontend folders

```
frontend/src/
  app/          router, query client, layout shell, auth guard
  pages/        one file per screen: Login, Scans, NewScan, Scan, AdminRules, AdminAudit, Privacy, NotFound, Landing
  features/
    scan/       sheet, marks, item list, risk banner, progress steps, downloads
    review/     review card, keyboard answers, undo
    admin/      rules table, reveal form, audit table, verify banner
  ui/           Button, Badge, Banner, Toast, Dialog, Table, SegmentedControl, FileDrop, Skeleton, EmptyState, Field
  api/          typed client (types generated from the backend OpenAPI schema), query hooks
  styles/       tokens, Tailwind theme, font faces
```

---

## 5. Data flow

### 5.1 J1: clean a document

```
1  Browser  POST /api/v1/scans (file or text)
2  API      check session → check size, type, contents → encrypt + save file → insert scan(queued) → enqueue → 202 {id}
3  Browser  GET /api/v1/scans/{id} every 1 s
4  Worker   decrypt file → parse (offset map) → run graph:
              detectors in parallel → fuse → review gate → policy (HMAC tokens, vault) → verify ⟲ → finalize
            after each node: update scan.step / scan.round
5  Worker   save decisions (offsets, type, action, reason, token; no raw values)
            save cleaned output (encrypted) → scan(done, risk) → audit "scan_completed"
            delete the scan's checkpoints
6  Browser  sees done → GET /scans/{id}/result → renders sheet + redaction pass
7  Browser  GET /scans/{id}/download?kind=cleaned|report
```

### 5.2 J2: review

```
worker hits interrupt → scan(needs_review), review items stored in the checkpoint
browser GET /scans/{id} → status needs_review + items (index, type, score, reason, context snippet)
browser POST /scans/{id}/answers [{index, verdict}] → validated → enqueued
worker resumes from checkpoint → beliefs updated → audit "review" → continues as J1 step 4
```

### 5.3 J3: show a real value (admin)

```
POST /api/v1/admin/reveal {token, reason}
→ require admin → vault.reidentify (role + reason checked again in the domain)
→ audit "reidentify" written BEFORE the value is returned → 200 {value}
refused attempts → audit "reidentify_denied" → 403
```

### 5.4 J4: verify the log (admin)

```
POST /api/v1/admin/audit/verify → AuditLog.verify(anchor from /data/audit.anchor.json)
→ 200 {ok, checked, first_bad_seq, reason}
```

### 5.5 Where personal data goes

| Data | Where it exists | Form | Removed |
| --- | --- | --- | --- |
| Original file | `files/` | AES-GCM encrypted | 7 days (D8) |
| Original text | Worker memory; checkpoints while a scan is open | Encrypted in `checkpoints.db` | When the scan ends; leftover checkpoints after 1 day |
| Cleaned output | `files/` | Encrypted | 7 days |
| Real values behind tokens | `vault` table | AES-GCM, bound to its token | When no remaining scan uses the token (D8, DATABASE 3.7) |
| Decisions, report | `decisions` table, report file | Offsets, types, actions, tokens only | With the scan |
| Audit log, app logs | `audit_log` table, stdout | Never raw values | Audit permanent; logs per host |

---

## 6. Folder structure

```
privacy-guardian/
├── backend/
│   ├── app/
│   │   ├── api/            ⬜ routes (auth, scans, admin, health), schemas, deps, errors
│   │   ├── services/       ⬜ scans, review, downloads, auth, admin, retention
│   │   ├── storage/        ⬜ db engine, SQLAlchemy models, repositories, sql stores, encrypted file store
│   │   ├── runtime/        ⬜ lifespan (model load, worker, cleanup), scan worker
│   │   ├── migrations/     ⬜ Alembic versions
│   │   ├── detectors/      ✅ rules, validators, NER, context
│   │   ├── fusion/         ✅ fuse, linking, normalize, risk
│   │   ├── policy/         ✅ beliefs, utility, actions
│   │   ├── graph/          ✅ state, build, serde
│   │   ├── parsers/        ✅ files, chunking, base
│   │   ├── crypto/         ✅ keys, tokens, vault, audit, filestore, services
│   │   ├── eval/           ✅ gold set loader
│   │   ├── cli.py          ✅ scan, reidentify, audit; ⬜ create-user
│   │   ├── config.py       🟡 settings (extend in M5)
│   │   └── main.py         🟡 app factory (health only today)
│   ├── tests/              ✅ unit + graph + crypto; ⬜ api/, storage/
│   ├── pyproject.toml
│   └── alembic.ini         ⬜
├── frontend/               ⬜ (section 4.1)
├── ml/                     ✅ training notebook, scripts
├── data/                   ✅ eval sets, samples (runtime data is NOT here; it is /data in the container)
├── docs/                   ✅ PRD, DESIGN, ARCHITECTURE, SRS (superseded), decisions/, results/
├── Dockerfile              🟡 becomes multi-stage (frontend + backend + model)
├── docker-compose.yml      🟡 one service + one volume (Postgres service removed, D2)
├── .env.example            ✅ extend in M5
└── .github/workflows/ci.yml ✅ add frontend job in M6
```

---

## 7. Database

### 7.1 Files and settings

- `app.db`: all app tables. `checkpoints.db`: LangGraph only (separate so it can be cleaned or encrypted without touching app data).
- SQLite settings at connect: WAL journal (readers never block the writer), foreign keys on, busy timeout 5 s, synchronous NORMAL.
- **One writer at a time** is fine: the worker and the API write small rows; SQLite handles this load easily.

### 7.2 Tables (MVP)

The full data model (10 tables, types, keys, constraints, indexes, retention, backups) is in **DATABASE.md**, which wins over this section for anything about data.

### 7.3 Access rules

- Only `storage/` touches SQLAlchemy. Services call repositories; repositories return plain domain objects.
- Every write that belongs together runs in **one transaction** in a service (e.g. save decisions + set `done` + write audit record).
- **Migrations:** Alembic, one revision per schema change; CI runs `upgrade head` on an empty database and runs the API tests on it.
- **Retention job:** a background thread runs at startup and every 24 h: deletes expired files, vault rows, decisions and scans; deletes checkpoints older than 1 day; writes one audit event with counts only.

---

## 8. Authentication and authorization

### 8.1 Authentication

| Item | Choice |
| --- | --- |
| Method | Email + password; server-side sessions (D14) |
| Password storage | bcrypt, cost 12 |
| Session | 32 random bytes in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie; only its hash is stored |
| Lifetime | Expires after 8 hours idle or 7 days total; logout deletes the row |
| Login protection | Same message for unknown email and wrong password; 5 failed tries per email+IP per 5 minutes, then wait 1 minute (in-memory counter, fine for one process) |
| Cross-site requests | `SameSite=Strict` + the API rejects state-changing requests whose `Origin` header is not the app's own |
| First admin | Created by `python -m app.manage create-user EMAIL --role admin` (password asked, never on the command line), or from `ADMIN_EMAIL` / `ADMIN_PASSWORD` once at first start if no users exist |
| New login | Gets a new session id every time; a session cookie the browser already sent is ended, so logging in again never leaves an old session alive |
| Dead cookie | A 401 for a cookie that no longer works also clears that cookie |
| Logout | Idempotent: `204` even without a session, so a stale tab can always log out |
| Browser side | The app never sees the session (HttpOnly). Route guards only decide what to show; the server checks every request. A 401 anywhere drops all cached data and returns to `/login?next=…` (only paths inside the app are accepted as `next`) |
| Not in MVP | Sign-up page, password reset, email, SSO (PRD 14). Users are created by an admin with `app.manage` |

### 8.2 Authorization

Checked in API dependencies **and** again in services for anything sensitive.

| Rule | Where |
| --- | --- |
| Every `/api/v1/*` route except `auth/login` and `health` needs a session | API dependency |
| A user can only read, review, download or delete **their own** scans; anything else returns 404 (not 403, so ids cannot be probed) | Service query filters by owner |
| `/api/v1/admin/*` needs role `admin` | API dependency |
| Reveal checks role and reason again and logs refusals | Domain (`Vault.reidentify`) |
| Every admin service method checks the role again | `AdminService` (a routing mistake cannot open an admin action) |
| A test discovers every API route and checks it for anonymous, user and admin callers | `tests/test_authz.py` |
| Admins do not see other users' documents (PRD 9) | No admin route returns document text |

---

## 9. API architecture

### 9.1 Conventions

- REST + JSON under `/api/v1`. Uploads are `multipart/form-data`. Downloads stream a file with `Content-Disposition: attachment`.
- OpenAPI schema from FastAPI is the contract; the frontend's TypeScript types are generated from it in CI, so a breaking change fails the build.
- **Error shape** (every non-2xx):
  `{ "error": { "code": "file_too_large", "message": "File too large (max 10 MB).", "field": "file", "request_id": "…" } }`
  `message` is safe to show the user and matches PRD section 12 wording.
- IDs are UUIDs. Lists are paginated with `?limit=&cursor=`.

### 9.2 Endpoints (MVP)

> **API.md** is the full, current API contract (19 endpoints, formats, errors, limits) and wins over this summary.

| Method | Path | Role | Purpose | Status codes |
| --- | --- | --- | --- | --- |
| GET | `/health` | public | Liveness + `model_ready` | 200 |
| POST | `/auth/login` | public | Start session | 204, 401, 429 |
| POST | `/auth/logout` | user | End session | 204 |
| GET | `/auth/me` | user | Current user, role | 200, 401 |
| POST | `/scans` | user | Upload file or text, start scan | 202, 413, 415, 422 |
| GET | `/scans` | user | My scans (Needs review first, then newest) | 200 |
| GET | `/scans/{id}` | owner | Status, step, round; review items when `needs_review`; risk when `done` | 200, 404 |
| POST | `/scans/{id}/answers` | owner | Review answers, resume | 202, 404, 409 (not waiting), 422 |
| GET | `/scans/{id}/result` | owner | Items, decisions, risk, tokens, rounds, timings (for S4) | 200, 404, 409 (not done) |
| GET | `/scans/{id}/download?kind=cleaned\|report` | owner | Cleaned file (D4 format) or JSON report | 200, 404, 409 |
| DELETE | `/scans/{id}` | owner | Delete scan, files, vault entries now | 204, 404 |
| GET | `/admin/rules` | admin | Fixed actions per type | 200 |
| PUT | `/admin/rules` | admin | Save fixed actions | 200, 422 |
| POST | `/admin/reveal` | admin | Token + reason → real value (logged) | 200, 403, 404, 422 |
| GET | `/admin/audit` | admin | Audit events, newest first, paginated | 200 |
| POST | `/admin/audit/verify` | admin | Verify chain against anchor | 200 |
| POST | `/admin/audit/anchor` | admin | Save the current anchor | 200 |

All paths above are under `/api/v1` except `/health`.

### 9.3 Polling contract (D6)

- `GET /scans/{id}` is cheap (one row read) and returns `status`, `step` (1–5), `step_label`, `round`, `max_rounds`, `updated_at`.
- The client polls every 1 s while `queued`/`running`, stops on `needs_review`, `done` or `failed`, and backs off to 5 s if the tab is hidden.

---

## 10. External services

| Service | Used for | When | MVP |
| --- | --- | --- | --- |
| Hosting provider | Running the container + one persistent volume | Runtime | Yes, **D13 (reopened)** |
| Model weights store | Holding the ~260 MB NER weights (now in Google Drive) | **Build time only** (baked into the image) | Yes, **D16** |
| GitHub + Actions | Code, CI, required checks | Development | Yes (done) |
| Hugging Face Hub (dataset) | ai4privacy training data | Training only (Colab) | Done |
| Anything at runtime | — | — | **None.** No analytics, no CDN fonts, no LLM, no error-tracking SaaS (it would receive request data) |

---

## 11. AI architecture

| Part | MVP design | Status |
| --- | --- | --- |
| Models | One fine-tuned DistilBERT (NER), CPU only. No LLM | ✅ |
| Loading | Loaded once in the app's startup; `/health` reports `model_ready`; scans queue until ready ("Preparing the model", DESIGN 8) | ⬜ |
| Workflow | LangGraph graph (ADR-0018): parallel detectors, source-aware fusion, review interrupt, utility policy with risk loop, stricter verifier loop (max 3 rounds) | ✅ |
| Long text | Overlapping 1,500-character chunks with edge repair (ADR-0019) | ✅ |
| Learning | Two Beta beliefs per PII type, updated only from review answers, stored in `beliefs` (ADR-0016) | ✅ logic, ⬜ table |
| Determinism | Same input + same beliefs + same keys = same output; model in eval mode, no sampling | ✅ |
| Versioning | `model_version` (weights hash) saved on every scan and in the report | ⬜ |
| Evaluation | Gold sets in `data/eval`; NER outputs cached so fusion changes are scored without the model; held-out set v2 before any claim (D9) | ✅ / ⬜ v2 |
| Explainability | Every decision stores sources, score, action and reason; S4 shows them | ✅ logic |
| Safety of the AI part | The model never sees anything but the document text; no tool calls, no network | ✅ |

---

## 12. Environment configuration

All settings come from environment variables (read once by `app/config.py`). `.env` for local runs only; never committed.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `ENV` | no | `dev` | `dev` or `prod`. In `prod`: DEV keys refused, `Secure` cookies forced, docs page off |
| `DATA_DIR` | no | `/data` | Holds `app.db`, `checkpoints.db`, `files/`, anchor file |
| `PG_TOKEN_KEY` | **prod** | DEV key in dev | HMAC pseudonyms (ADR-0020) |
| `PG_AUDIT_KEY` | **prod** | DEV key in dev | Audit chain |
| `PG_VAULT_KEY` | **prod** | DEV key in dev | Vault |
| `PG_STORAGE_KEY` | **prod** | DEV key in dev | Encrypting files and checkpoints at rest (D15) |
| `NER_MODEL_PATH` | no | `/app/model` | Model folder inside the image |
| `NER_THRESHOLD` | no | `0.5` | Fusion threshold |
| `RETENTION_DAYS` | no | `7` | Documents, outputs, vault (D8) |
| `MAX_UPLOAD_MB` | no | `10` | FR-01 |
| `SESSION_IDLE_HOURS` / `SESSION_MAX_DAYS` | no | `8` / `7` | Section 8 |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | no | — | Creates the first admin once, only if no users exist; remove after first start |
| `PUBLIC_ORIGIN` | **prod** | `http://localhost:8000` | Used for the `Origin` check |
| `LOG_LEVEL` | no | `INFO` | |

Key rules (ADR-0020): four different keys, each at least 32 bytes, rotated by appending a new `id:hex` at the end.

---

## 13. Error handling

### 13.1 Layers

| Layer | Does |
| --- | --- |
| Domain | Raises specific errors: `ParseError`, `VaultError`, `AccessDeniedError`, `KeyConfigError` |
| Services | Turn domain errors into app errors with a stable `code`; never swallow them |
| API | One exception handler maps app errors to HTTP status + the error shape (9.1); anything unexpected → 500 with only a `request_id` |
| Worker | Catches everything per scan: sets `failed`, `error_code`, the failing step; the scan stays resumable from its last checkpoint; the worker continues with the next scan |
| Frontend | TanStack Query retries GETs twice; never retries POSTs; shows the `message` from the error shape in the right place (field, region, page; DESIGN 8) |

### 13.2 Error codes (MVP)

`file_too_large`, `unsupported_type`, `pdf_no_text`, `file_unreadable`, `empty_input`, `not_found`, `not_waiting_for_review`, `invalid_answers`, `scan_not_done`, `auth_failed`, `rate_limited`, `session_expired`, `forbidden`, `reason_too_short`, `unknown_token`, `vault_integrity`, `model_not_ready`, `internal`.

### 13.3 Logging

- Structured JSON lines to stdout: time, level, request_id, user_id, scan_id, route, status, duration, error_code.
- **Never logged:** document text, item values, tokens' real values, passwords, session ids, keys. A test scans the captured log output of a full scan for every known sample value and fails if one appears (PRD success criterion 7).

---

## 14. Security boundaries

### 14.1 Trust zones

```
[Untrusted]  Browser, uploaded files, every request field
     │  validated at the API boundary
[App]        FastAPI + worker + domain code (one process)
     │  only via storage layer
[Data]       /data volume: SQLite files, encrypted files
     │
[Secrets]    environment variables (4 keys, admin bootstrap) - never written to disk or logs
```

### 14.2 Controls

| Threat | Control |
| --- | --- |
| Oversized or fake files | Size limit checked while streaming (stop at 10 MB); type by extension **and** first bytes (`%PDF`, ZIP for DOCX); text must decode |
| DOCX zip bomb | Before parsing, sum the uncompressed sizes in the ZIP; refuse above 50 MB or above 100 entries per MB |
| Pathological PDFs | Parse in the worker with a time limit per scan (60 s); failure becomes `file_unreadable` |
| Reading another user's scan | Owner filter on every query; 404 for others' ids |
| Session theft / CSRF | `HttpOnly`, `Secure`, `SameSite=Strict` cookie; `Origin` check on writes; only session hashes stored |
| Password guessing | bcrypt + rate limit + uniform error |
| XSS | React escapes by default; document text is rendered as text, never as HTML; strict CSP: `default-src 'self'`, no inline scripts, `frame-ancestors 'none'` |
| Other headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, HSTS in prod |
| Data at rest | Files and checkpoints encrypted (AES-GCM, `PG_STORAGE_KEY`); vault values encrypted and bound to their token (`PG_VAULT_KEY`) |
| Tampering with the audit log | HMAC chain + anchor (ADR-0020) + SQLite triggers blocking UPDATE/DELETE |
| Tampered checkpoint | Allow-list deserializer (ADR-0018) + authenticated encryption |
| Brute-forcing tokens back to values | HMAC with a secret key (ADR-0002) |
| Key leak | Four separate keys limit the damage; rotation by key id; DEV keys refused in prod |
| Data kept too long | Daily retention job (section 7.3) |
| Supply chain | Pinned versions; Dependabot alerts; image built in CI from the lockfiles |

### 14.3 Known limits (accepted for MVP)

- Someone with the server's environment **and** disk can read everything; this is a single-server app.
- The audit anchor is a local file (D10); a production setup copies it off the server.
- In-memory login rate limits reset on restart.

---

## 15. Testing approach

| Level | What | Tool | Status |
| --- | --- | --- | --- |
| Unit | Validators, fusion, linking, risk, beliefs, policy, crypto, parsers, chunking (incl. property tests) | pytest, Hypothesis | ✅ 125 tests, 96% |
| Graph | Parallel fan-out, review interrupt and resume, verifier loop, crypto in graph | pytest, fake NER | ✅ |
| Real-run regressions | Bugs found by running the real model, each with a test | pytest | ✅ |
| Storage | SQL stores pass the **same** tests as the in-memory stores; audit triggers block edits; migrations upgrade an empty DB | pytest, temp SQLite | ✅ |
| API | Every endpoint: happy path, error codes, **authorization matrix** (user vs admin vs other user), upload limits, zip bomb | httpx TestClient | ✅ |
| Failures and edges | Locked database (503 busy), disk full, model crash + retry, empty files, Windows line endings, emoji offsets, merged DOCX cells, filename tricks; property tests for fusion and output rebuild | pytest, Hypothesis | ✅ (QA report 2026-11-20) |
| Privacy | Full scan through the API; captured logs and audit payloads contain no sample value | pytest | ✅ |
| Restart | Pause at review, rebuild the app (new process objects), answer, scan completes | pytest | ✅ |
| Frontend logic | Mark rendering from offsets, keyboard handler, error mapping | Vitest | 🟡 auth, guards, error mapping ✅; screens come with P14–P17 |
| End to end | J1 clean a document, J2 review, J4 tamper-and-verify, in a real browser against the real container (fake model) | Playwright | 🟡 container smoke scan in CI ✅ (`scripts/smoke.sh`); browser journeys with the screens (P18.4) |
| Accuracy | Gold set v1 (cached NER) on every run; held-out v2 before any claim | eval script | ✅ / ⬜ |

CI (required to merge): ruff, mypy, pytest with coverage ≥ 70%, layer-import check, Alembic upgrade, frontend type check + lint + Vitest + build, Docker build. Playwright runs on `main` and before tags.

---

## 16. Deployment

### 16.1 Image

One multi-stage Dockerfile:
1. **Frontend stage:** install with the lockfile, build static files.
2. **Model stage:** fetch the NER weights (D16) and verify their SHA-256 (`model-hf`), or build a tiny random model for CI (`model-fake`, chosen with `MODEL_SOURCE`).
3. **Runtime stage:** Python slim + CPU-only PyTorch + backend + static files + model (root-owned, read-only to the app). Runs as a non-root user. Exposes one port. Hugging Face is switched off at runtime (`HF_HUB_OFFLINE=1`).

The app runs Alembic migrations at startup (with a backup first), then serves with one Uvicorn worker (one process: the model and the scan queue are in memory).

### 16.2 Runtime

- **One container + one persistent volume** mounted at `/data`. Nothing else is needed.
- Health check: `/health` (ready when `model_ready` is true).
- Memory: about 1–1.5 GB (PyTorch + model); CPU: 1–2 cores.
- Backups (MVP): a copy of `/data` before each release; SQLite's online backup makes a consistent copy while running.
- Releases: tag `vX.Y.Z` on `main` → CI builds the image → deploy that image.

### 16.3 Local

`docker compose up` runs the same image with a local `./data` volume and DEV keys. Without Docker: backend with `uvicorn`, frontend with Vite's dev server proxying `/api` to the backend.

---

## 17. MVP vs future scale

| Pressure | MVP | Next step (no domain rewrite) |
| --- | --- | --- |
| More users at once | 1 worker thread, SQLite | Postgres (swap storage implementations; Alembic already in place) + N worker processes reading a `scans` queue table (`SELECT … FOR UPDATE SKIP LOCKED`) |
| Faster scans | CPU PyTorch | ONNX Runtime with an int8 model (smaller, ~2–3× faster on CPU) |
| Bigger files | 10 MB, in-memory parse | Stream pages; raise limits per plan |
| More than one server | Not supported | Move files to object storage; sessions and rate limits to Postgres; workers as their own container |
| Many organisations | One per deployment (D3) | `org_id` on beliefs, rules and scans (the domain already keys beliefs by org) |
| Live progress | Polling | Server-Sent Events from the same endpoint |
| Stronger audit proof | Local anchor | Scheduled anchor to a separate store; Ed25519-signed reports (FR-28) |
| Scanned PDFs | Refused with a clear message | OCR stage before parsing |
| Hard cases | No LLM | Local LLM detector behind the same detector interface (FR-09), still no data leaves the server |

---

## 18. Decisions (D13 to D17 approved by the owner on 2026-11-19, ADR-0022)

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| **D13** | **Hosting (reopens D1).** Hugging Face's docs say a Space's disk is lost on every restart, so SQLite there needs a mounted storage bucket. Community reports from mid-2026 also say new free Docker Spaces now need a PRO subscription. Both break the "free + persistent" plan behind D1 | (a) HF Spaces with PRO + a storage bucket at `/data` (b) a small VM (student cloud credits or an always-free tier, **check current terms**) running `docker compose` with a disk volume (c) a free container host with a temporary disk, accepting that the demo resets on restart | **(b)**. One container + one disk is exactly this architecture; nothing changes if the host changes later. Use (c) only as a fallback demo that seeds a sample admin and samples on every start |
| **D14** | Session cookies instead of JWT (SRS FR-32 said JWT) | (a) server-side sessions (b) JWT | **(a)**: one origin, revocable at logout, no token storage in the browser |
| **D15** | A 4th key `PG_STORAGE_KEY` to encrypt uploaded files and graph checkpoints at rest (PRD 10 asks for files encrypted at rest; checkpoints hold raw text while a scan is open) | (a) 4th key, encrypt both (b) no at-rest encryption (c) reuse the vault key | **(a)**: keeps one key per purpose (ADR-0002); uses the existing `cryptography` library, no new dependency |
| **D16** | Where the model weights live (now Google Drive) | (a) a private Hugging Face model repo, downloaded at image build (b) Git LFS in this repo (c) stay on Drive | **(a)**: versioned, free for models, fetched once at build, never at runtime |
| **D17** | One scan at a time (single worker thread) | (a) one worker thread (b) a task queue service | **(a)** for MVP; see section 17 for the next step |

### Sources for D13
- [Hugging Face Hub docs: Spaces storage](https://huggingface.co/docs/hub/spaces-storage): "This disk space is ephemeral, meaning its content will be lost if your Space restarts or is stopped"; storage buckets are the recommended way to persist data.
- [Hugging Face forum: community complaint about free CPU Basic Spaces](https://discuss.huggingface.co/t/official-community-complaint-revert-free-cpu-basic-spaces-and-remove-anti-developer-sdk-restrictions/177703) (user reports, not an official announcement): new free Docker Spaces refused with "hosting Gradio and Docker Spaces on free cpu-basic requires a PRO subscription".

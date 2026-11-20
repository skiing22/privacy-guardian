# Implementation plan: Privacy Guardian Agent v2

> Built from PRD.md, DESIGN.md, ARCHITECTURE.md, DATABASE.md, API.md and AGENTS.md. No application code here.
>
> **Starting point:** `main` at `v0.5.0`. Done and tested: detectors, NER, fusion, linking, risk, beliefs, utility policy, LangGraph graph with review interrupt and verifier loop, parsers and chunking, crypto (tokens, vault, audit chain), CLI. 125 tests, 96% coverage.
>
> **What is left:** the web backend (M5), the web app (M6), deployment and polish (M7). This plan breaks those into **23 phases (P0 to P22)**, each one or a few pull requests, each independently testable.

---

## How to read this plan

- **Phases are ordered by dependency.** A phase starts only when its prerequisites are merged with green CI.
- **Tasks** are sized for one pull request each (roughly half a day to a day). Task ids (e.g. `P3.2`) go in branch names and commit messages, next to FR ids.
- **Every phase ends** with: all AGENTS.md 9.3 checks green, docs updated (AGENTS.md 10), checklist ticked.
- **Owner tasks** (marked 👤) need you, not the coding agent: approvals, accounts, writing the test set, uploading weights.
- Phases marked **∥** can run in parallel with the main line.

### Phase map

```
M5 backend   P0 docs ─► P1 config ─► P2 database ─► P3 stores ─► P4 checkpoints
                             │                          │
                             └─► P5 auth ◄──────────────┘
                                   │
             P6 output writers ─► P7 scan worker ─► P8 scan API ─► P9 admin API ─► P10 retention ─► P11 container   (tag v0.6.0)

M6 frontend  P12 foundation ─► P13 UI kit ─► P14 S1–S3 ─► P15 S4 run+review ─► P16 S4 result ─► P17 admin ─► P18 S7/S8, a11y, e2e   (tag v0.7.0)

M7 ship      P19 eval set v2 ∥ (any time, 👤) ─► P20 deploy ─► P21 README + landing ─► P22 release   (tag v1.0.0)
```

---

## M5: Backend

### P0. Land the documents and open decisions

**Goal:** the repo holds the source of truth before any code depends on it.

| Task | Detail |
| --- | --- |
| P0.1 👤 | ✅ Done: D13 to D17 approved 2026-11-19 (ADR-0022) |
| P0.2 | One docs pull request: `docs/PRD.md`, `DESIGN.md`, `ARCHITECTURE.md`, `DATABASE.md`, `API.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md` (repo root), ADR-0021 (D1–D12), ADR-0022 (D13–D17), SRS marked superseded, decisions README |
| P0.3 | Replace the milestone checklist with this plan's phases |

- **Files:** `docs/*`, `AGENTS.md`, `docs/decisions/0021-*.md`, `0022-*.md`
- **Prerequisites:** none
- **DB/API changes:** none
- **Tests:** CI still green (docs only)
- **Done when:** all docs are on `main`; D13–D17 have a recorded answer

### P1. Configuration, keys, logging and guard rails

**Goal:** every later phase reads settings, keys and logs the same way, and CI enforces the layer rules.

| Task | Detail |
| --- | --- |
| P1.1 | Extend `config.py` with every runtime variable in API.md 10.1 (types, defaults, `prod` validation: no DEV keys, `PUBLIC_ORIGIN` required) |
| P1.2 | Add the 4th key purpose `storage` (`PG_STORAGE_KEY`) to `KeyRing`, `.env.example`, ADR-0020 consequence note (D15) |
| P1.3 | Structured JSON logging with `request_id`, `user_id`, `scan_id`; a log filter that drops known body fields; no document text ever |
| P1.4 | CI: layer-import check (domain must not import api/services/storage/FastAPI/SQLAlchemy, AGENTS.md 3.1); core job runs without PyTorch |
| P1.5 | `docker-compose.yml`: one service + `./data` volume; remove the Postgres service (D2) |

- **Files:** `backend/app/config.py`, `app/crypto/keys.py`, `app/logging.py` (new), `.env.example`, `.github/workflows/ci.yml`, `docker-compose.yml`, `scripts/check_layers.py` (new)
- **Prerequisites:** P0
- **DB/API changes:** none
- **Tests:** settings load and `prod` refusals; 4 distinct keys enforced; logging redaction test; layer check fails on a planted bad import
- **Done when:** app starts in `dev` with no env set; refuses to start in `prod` with missing/DEV/reused keys; CI has the layer check

### P2. Database foundation

**Goal:** an empty `app.db` with the full DATABASE.md schema, created by migrations.

| Task | Detail |
| --- | --- |
| P2.1 ✅ | `storage/db.py`: engine for `DATA_DIR/app.db`; on connect set WAL, `foreign_keys`, `busy_timeout`, `synchronous=NORMAL`, `secure_delete` |
| P2.2 ✅ | Done as raw SQL DDL + SQLAlchemy Core instead of ORM models (ADR-0023). Was: SQLAlchemy models for the 10 tables, `STRICT`, every `CHECK`, FK action and index in DATABASE.md 3 and 6 |
| P2.3 ✅ | Alembic set up (batch mode); revision `0001_initial` incl. `audit_log` append-only triggers |
| P2.4 ✅ | Enum-sync test: SQL `CHECK` lists equal the Python enums |
| P2.5 ✅ | CI: upgrade empty DB → downgrade → upgrade |

- **Files:** `backend/app/storage/{db,models}.py`, `backend/app/migrations/`, `backend/alembic.ini`, `pyproject.toml` (SQLAlchemy, Alembic: already approved in ARCHITECTURE 1.1)
- **Prerequisites:** P1
- **DB changes:** all 10 tables (first migration)
- **Tests:** each `CHECK` rejects a bad row (one test per table); `done` scan without risk rejected; UPDATE/DELETE on `audit_log` raises; FK cascades behave as in DATABASE 4
- **Done when:** `alembic upgrade head` builds the schema; CI migration step green

### P3. Storage layer

**Goal:** SQL versions of every store the domain already uses, plus repositories and the encrypted file store.

| Task | Detail |
| --- | --- |
| P3.1 ✅ | Shared **contract tests** for `BeliefStore`, `TokenRegistry`, `VaultStore`, `AuditStore`, run against the in-memory versions first (they must pass unchanged) |
| P3.2 ✅ | `SqlBeliefStore`, `SqlTokenRegistry` (+ `UNIQUE(full_mac, key_id)`) pass the contract tests |
| P3.3 ✅ | `SqlVaultStore` and `SqlAuditStore` (append in `BEGIN IMMEDIATE`, seq + prev_mac read in the same transaction) pass the contract tests; audit verify works on SQL rows |
| P3.4 ✅ | Encrypted file store: `files/{scan_id}.{kind}`, AES-GCM with `PG_STORAGE_KEY`, associated data `scan_id|kind|key_id` |
| P3.5 ✅ | Repositories: users, sessions, rules, scans/scan_files/decisions **owner-scoped**; a separate `storage/worker_repo.py` (unscoped) for worker and retention |

- **Files:** `backend/app/storage/{stores,files,repos,worker_repo}.py`, `tests/storage/`
- **Prerequisites:** P2
- **DB changes:** none (uses P2 schema)
- **Tests:** contract tests ×2 implementations; file store: round trip, wrong scan id fails, tampered byte fails; owner-scoped repo never returns another owner's scan; layer check forbids `api` importing `worker_repo`
- **Done when:** the CLI demo can run on SQL stores by a flag; all contract tests green for both implementations

### P4. Encrypted graph checkpoints

**Goal:** paused and crashed scans survive a restart, with raw text encrypted at rest (FR-23, D15).

| Task | Detail |
| --- | --- |
| P4.1 ✅ | `SqliteSaver` on `DATA_DIR/checkpoints.db` with the existing allow-list serializer |
| P4.2 ✅ | Encryption: LangGraph `EncryptedSerializer` with a small cipher adapter over `cryptography` AES-GCM using `PG_STORAGE_KEY` (no new dependency) |
| P4.3 ✅ | Delete a scan's checkpoint thread (used when a scan ends or is deleted) |

- **Files:** `backend/app/graph/checkpoints.py` (new), `graph/serde.py`
- **Prerequisites:** P1 (keys), P3 not required
- **DB changes:** `checkpoints.db` created by the library
- **Tests:** pause at review → drop all objects → new graph + saver → resume completes (the existing in-memory restart test, now on SQLite); raw sample text not found in the checkpoint file bytes; tampered checkpoint fails to load
- **Done when:** FR-23 met on disk; the "Postgres saver" checklist item is closed as superseded by D2

### P5. Authentication, middleware and errors

**Goal:** the API skeleton every endpoint plugs into: sessions, roles, headers, error format, rate limits.

| Task | Detail |
| --- | --- |
| P5.1 ✅ | App factory: routers under `/api/v1`, request-id middleware, security headers (API.md 2.2), `no-store`, `Origin` check on writes |
| P5.2 ✅ | Error model: app errors with the API.md 2.4 codes; one global handler; `500` hides details |
| P5.3 ✅ | Users: bcrypt hashing; `cli create-user`; one-time admin bootstrap from env (writes `user_created`) |
| P5.4 ✅ | Sessions: create, look up by hash, touch at most once a minute, expiry; `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| P5.5 ✅ | Auth dependencies: `current_user`, `require_admin`; disabled users rejected |
| P5.6 ✅ | In-memory rate limiter (API.md 7) with `Retry-After`; login limits wired |

- **Files:** `backend/app/main.py`, `app/api/{deps,errors,auth}.py`, `app/api/schemas/auth.py`, `app/services/auth.py`, `app/middleware.py`, `app/cli.py`, `pyproject.toml` (`bcrypt`)
- **Prerequisites:** P3 (users, sessions repos)
- **API changes:** endpoints 2, 3, 4 (API.md 4.2–4.4); `/health` returns API.md 4.1 shape (model flag stubbed)
- **Tests:** login success/failure (same message), lockout and `Retry-After`, expired/idle sessions, cookie flags, `Origin` rejection, headers present on every response, error body shape, unknown field → `422`
- **Done when:** a user created by CLI can log in and call `/auth/me`; every error matches API.md

### P6. Output writers and result building ∥ (after P3)

**Goal:** turn decisions into the cleaned file, the result view and the report (FR-30, D4), independent of HTTP.

| Task | Detail |
| --- | --- |
| P6.1 ✅ | Cleaned segments across rounds: apply round 1 decisions to the original, later rounds to the previous output, keeping `item_idx` per segment (API.md 4.9) |
| P6.2 ✅ | Writers: TXT/MD (text), CSV (cell by cell via the parser's offset map), DOCX (paragraph and table-cell text via the offset map, keeping paragraph style), PDF → `.txt` |
| P6.3 ✅ | JSON report builder (API.md 4.10): offsets, types, actions, tokens; never values |
| P6.4 ✅ | `output` text per item from the existing `render()` |

- **Files:** `backend/app/output/{segments,writers,report}.py` (new; domain layer), `app/parsers/files.py` (expose what writers need, no behaviour change)
- **Prerequisites:** P3 not needed; uses domain only
- **DB/API changes:** none yet
- **Tests:** segments join to exactly the cleaned text (property test over random decisions and 1–3 rounds); each writer round-trips through its parser and contains no protected sample value; DOCX keeps paragraph count; report has no value from the input
- **Done when:** the CLI can write a cleaned DOCX and CSV and a report from a scan

### P7. Scan service and worker

**Goal:** scans run in the background against the database, with progress, review pauses, recovery and timeouts.

| Task | Detail |
| --- | --- |
| P7.1 ✅ | Upload validation (domain helper): streaming size limit, extension + magic bytes, DOCX uncompressed-size check, text decoding (API.md 4.5) |
| P7.2 ✅ | Model lifespan: load NER at startup in a thread; `model_ready` flag; `/health` real; worker waits until ready |
| P7.3 ✅ | Scan service: create scan (encrypt + save original, row `queued`), enqueue; worker thread with FIFO queue |
| P7.4 ✅ | Worker run: decrypt → parse (60 s timeout) → graph with SQL stores, admin `rules` → `PolicyConfig`, `thread_id = scan id`; stream node updates → `step`/`round`/`updated_at` |
| P7.5 ✅ | Finish: one transaction for decisions, cleaned file, `done` + risk, `scan_completed` audit (no filename); delete checkpoint thread |
| P7.6 ✅ | Review pause → `needs_review`; resume with answers (validated); `review` audit; beliefs updated through `SqlBeliefStore` |
| P7.7 ✅ | Failures → `failed` + `error_code` + step, checkpoint kept; startup recovery re-enqueues `queued`/`running` |

- **Files:** `backend/app/services/scans.py`, `app/runtime/{lifespan,worker}.py`, `app/parsers/validate.py` (new), `app/graph/build.py` (only if a hook is truly needed; prefer streaming)
- **Prerequisites:** P3, P4, P6
- **DB changes:** none (writes `scans`, `scan_files`, `decisions`, `tokens`, `vault`, `beliefs`, `audit_log`)
- **Tests (fake NER):** state machine transitions; progress steps recorded in order; review → answers → done; worker survives a failing scan and runs the next; restart mid-scan resumes; zip bomb and fake PDF rejected; no sample value in logs or audit payloads
- **Done when:** a scan submitted through the service finishes with the same output as the CLI on `data/samples/patient_note.txt`

### P8. Scan API

**Goal:** endpoints 5–12 exactly as API.md 4.5–4.12.

| Task | Detail |
| --- | --- |
| P8.1 ✅ | `POST /scans` (multipart, streaming limit), `GET /scans` (cursor, `status` filter) |
| P8.2 ✅ | `GET /scans/{id}` (status, step label, review items with context, risk, error) |
| P8.3 ✅ | `POST /scans/{id}/answers` (completeness rules, `409` repeat) |
| P8.4 ✅ | `GET /scans/{id}/result`, `GET /scans/{id}/download?kind=` (filenames by scan id, `no-store`) |
| P8.5 ✅ | `POST /scans/{id}/retry`, `DELETE /scans/{id}` (cascade + files + checkpoints + unused vault rows) |
| P8.6 ✅ | Scan rate limits (20/hour, 3 open) and polling exemption |

- **Files:** `backend/app/api/scans.py`, `app/api/schemas/scans.py`, `app/services/scans.py`
- **Prerequisites:** P5, P7
- **API changes:** endpoints 5–12
- **Tests:** every error code per endpoint; **authorization matrix** (owner 2xx, other user 404, admin 404 on others' scans, logged out 401); full J1 and J2 through HTTP; privacy test: no sample value in captured logs; OpenAPI schema snapshot
- **Done when:** journeys J1 and J2 pass end to end through the API with the fake NER

### P9. Admin API

**Goal:** endpoints 13–19 (API.md 4.13–4.19).

| Task | Detail |
| --- | --- |
| P9.1 ✅ | `GET/PUT /admin/rules` with `allowed_actions`; `rules_changed` audit |
| P9.2 ✅ | `POST /admin/reveal` (audit before value; denied attempts logged; 10/hour) |
| P9.3 ✅ | `POST /admin/beliefs/reset` |
| P9.4 ✅ | `GET /admin/audit` (`before_seq` paging, actor resolved to email), `POST /admin/audit/verify`, `POST /admin/audit/anchor` (anchor file in `DATA_DIR`) |

- **Files:** `backend/app/api/admin.py`, `app/api/schemas/admin.py`, `app/services/admin.py`
- **Prerequisites:** P5, P8 (a scan to reveal from)
- **API changes:** endpoints 13–19
- **Tests:** role checks on all; reveal refused without reason, logged when refused, fails closed if the audit write fails; tamper a row in the DB file → verify reports that `seq`; rule with a disallowed action → `422`; a rule changes the next scan's decision
- **Done when:** journeys J3, J4 and J5 pass through the API

### P10. Retention and backups

**Goal:** data is deleted on schedule and can be backed up and restored (DATABASE 10).

| Task | Detail |
| --- | --- |
| P10.1 ✅ | Retention job thread: the 6 steps of DATABASE 10.3, at startup and every 24 h; `retention` audit with counts |
| P10.2 ✅ | `cli backup` (SQLite online backup + files) and a pre-migration backup in the start script |
| P10.3 ✅ | Restore runbook in `docs/` (DATABASE 10.4) and a test of it |

- **Files:** `backend/app/services/retention.py`, `app/runtime/lifespan.py`, `app/cli.py`, `docs/runbook-backup-restore.md`
- **Prerequisites:** P8
- **DB changes:** none
- **Tests:** expired scan → rows, files, checkpoints gone; vault row kept while another scan uses the token, deleted after; orphan files removed; backup + restore round trip verifies the audit chain
- **Done when:** a scan created "8 days ago" (injected clock) is fully gone after one run

### P11. Container and model delivery

**Goal:** one image that runs anywhere with one volume (ARCHITECTURE 16).

| Task | Detail |
| --- | --- |
| P11.1 👤 | Create a private Hugging Face model repo and upload `ner-distilbert-v1`; note the commit hash and SHA-256 (D16) |
| P11.2 ✅ | Multi-stage Dockerfile: model stage (build secret `HF_TOKEN`, pinned revision, SHA-256 check, retries), runtime stage (CPU PyTorch, non-root, port, health check); frontend stage added in P12 |
| P11.3 ✅ | Done in the app instead of a script: startup backs up, migrates, then serves with one Uvicorn worker (ADR-0023) |
| P11.4 ✅ | CI: build the image (without the real model, using a tiny fake model stage) and run the API tests against the container |

- **Files:** `Dockerfile`, `docker/start.sh`, `docker-compose.yml`, `.github/workflows/ci.yml`, `ml/scripts/model_hash.py`
- **Prerequisites:** P10
- **Tests:** container health goes ready; data survives `docker compose down/up`; image contains no `.env`, keys or token (layer scan in CI)
- **Done when:** `docker compose up` runs the full backend locally with the real model; **tag `v0.6.0`** (M5 done)

---

## M6: Web app

### P12. Frontend foundation

**Goal:** the React app builds, talks to the API with generated types, and has the shell.

| Task | Detail |
| --- | --- |
| P12.1 ✅ | Vite + React + TypeScript strict, ESLint, Vitest; folders per ARCHITECTURE 4.1 |
| P12.2 ✅ | Tailwind theme from DESIGN.md tokens (colours, type styles, spacing, radius); Manrope + Geist Mono via Fontsource; Phosphor |
| P12.3 ✅ | OpenAPI → TypeScript generation script; typed client; error-body mapping; TanStack Query setup (retry rules from ARCHITECTURE 13.1) |
| P12.4 ✅ | Router with all routes; auth guard (`/auth/me`, redirect with `next`); app shell: floating nav, mobile menu, footer, skip link |
| P12.5 ✅ | Serve the build from FastAPI (SPA fallback for client routes); add the frontend stage to the Dockerfile; CI frontend job |

- **Files:** `frontend/*`, `backend/app/main.py` (static mount), `Dockerfile`, `ci.yml`
- **Prerequisites:** P5 (auth endpoints), P8 schema stable
- **Tests:** type generation in CI fails on a breaking API change; guard redirects; build succeeds
- **Done when:** logging in lands on an empty `/scans` page inside the shell, served by the backend

### P13. UI kit

**Goal:** the DESIGN.md section 5 components, once, with all states.

| Task | Detail |
| --- | --- |
| P13.1 ✅ | Button (4 variants, hover/press/focus/disabled/loading), Field (label, help, error), TextArea |
| P13.2 ✅ | Badge, TypeLabel, Banner, Toast, Dialog (focus trap), Skeleton, EmptyState |
| P13.3 ✅ | Table (stacks on phones), SegmentedControl, FileDrop |

- **Files:** `frontend/src/ui/*`, `frontend/src/styles/*`
- **Prerequisites:** P12
- **Tests:** Vitest + Testing Library for states and keyboard (dialog focus return, segmented control arrows); contrast of token pairs checked once
- **Done when:** every component in DESIGN 5 exists with its states; no raw hex or arbitrary sizes (lint rule)

### P14. Login, scan list, new scan (S1–S3)

**Goal:** a user can log in, see scans and start one.

| Task | Detail |
| --- | --- |
| P14.1 ✅ | S1 Login (shared error, rate-limit message) |
| P14.2 ✅ | S2 Scans: needs-review query + newest query, table, empty state, delete with dialog |
| P14.3 ✅ | S3 New scan: FileDrop or paste, client-side size/type pre-check, Start scan → S4 |

- **Files:** `frontend/src/pages/{Login,Scans,NewScan}.tsx`, `features/scan/*`, `api/` hooks
- **Prerequisites:** P13
- **Tests:** Vitest for form errors; Playwright smoke: log in → upload sample → lands on S4
- **Done when:** PRD loading/empty/error states for S1–S3 all reachable

### P15. Scan page: running and review (S4 part 1)

**Goal:** progress and the review flow (J2), keyboard first.

| Task | Detail |
| --- | --- |
| P15.1 ✅ | Polling hook (1 s, 5 s hidden, stop on final states); progress steps with round label and "Preparing the model" |
| P15.2 ✅ | Sheet with marks for review context; review card; answers with `1 2 3`, `↑ ↓`, undo (`Z`, 5 s); Submit answers |
| P15.3 ✅ | Failed state with Retry; session-expired keeps unsent answers |

- **Files:** `frontend/src/pages/Scan.tsx`, `features/scan/{Progress,Sheet,Mark}.tsx`, `features/review/*`
- **Prerequisites:** P14
- **Tests:** keyboard handler ignores inputs; answers payload shape; live-region announcements; Playwright J2
- **Done when:** a paused scan can be answered entirely by keyboard and continues

### P16. Scan page: result (S4 part 2)

**Goal:** the result view, the item list and downloads (J1, US-2 to US-4).

| Task | Detail |
| --- | --- |
| P16.1 ✅ | Original view: marks from `items` offsets; hover/focus type label; select ↔ panel row |
| P16.2 ✅ | Cleaned view from `cleaned_segments`; token hover outlines all occurrences; Compare view (desktop) |
| P16.3 ✅ | Risk banner (4 levels, plain sentence, clues), item list with reasons, unresolved-leaks message |
| P16.4 ✅ | Redaction pass (once per scan, reduced-motion instant); downloads (PDF → `.txt` label) |

- **Files:** `features/scan/{CleanedSheet,ItemList,RiskBanner,Downloads}.tsx`
- **Prerequisites:** P15
- **Tests:** marks render exactly at offsets (property test with random items); segments render the cleaned text exactly; redaction pass skipped under reduced motion; Playwright J1
- **Done when:** S4 matches DESIGN 12 at 390, 768, 1024 and 1440 px
- **As built:** below 1024 px the item list sits under the sheet instead of the three tabs in DESIGN 10 (Review and Risk already have their own places on the page); Compare only from 1024 px

### P17. Admin screens (S5, S6)

**Goal:** J3, J4, J5 in the browser.

| Task | Detail |
| --- | --- |
| P17.1 ✅ | S5 rules table (grouped by family, allowed actions only, Save rules); Reset learning (danger + dialog) |
| P17.2 ✅ | S5 Show a real value: form → confirm dialog → value box, auto-hide 60 s (pauses on focus/hover) |
| P17.3 ✅ | S6 audit table (paging, event labels, Geist Mono tokens); Verify log banner; tampered row outlined and scrolled into view; Save anchor |

- **Files:** `frontend/src/pages/{AdminRules,AdminAudit}.tsx`, `features/admin/*`
- **Prerequisites:** P9, P13
- **Tests:** non-admin cannot reach the routes (and API refuses anyway); reveal value not kept in query cache after hide; Playwright J4 (tamper the DB file in the test container → verify shows the row)
- **Done when:** J3, J4, J5 work in the browser

### P18. Static pages, accessibility and end-to-end

**Goal:** finish M6 to the DESIGN.md quality floor.

| Task | Detail |
| --- | --- |
| P18.1 ✅ | S7 Privacy and terms (states retention 7 days, backups 7 days, what is stored, who sees it); S8 404 |
| P18.2 ✅ | Accessibility pass (DESIGN 11): keyboard-only run of all journeys, focus never under the nav, axe checks in Playwright |
| P18.3 ✅ | Responsive pass at 320, 390, 768, 1024, 1440; touch targets ≥ 44 px |
| P18.4 ✅ | Playwright J1, J2, J4 in CI (`e2e` job, every push and pull request) |

- **Files:** `frontend/src/pages/{Privacy,NotFound}.tsx`, `e2e/*`, `ci.yml`
- **Prerequisites:** P16, P17
- **As built (P18.4):** the journeys run against the **real app** (FastAPI, SQLite, worker,
  built frontend) started by `e2e/server.py`, with one change: the model is swapped for a
  fixed name finder. The fake model in the container is random, so it never pauses a scan
  for review and J2 could not run against it. The container stays covered by the `docker`
  job (`scripts/smoke.sh`). Each run needs a fresh data folder, because J4 tampers with
  the audit log on purpose.
- **Done when:** all journeys pass in Playwright; no axe violations; **tag `v0.7.0`** (M6 done)

---

## M7: Evaluate, deploy, present

### P19. Held-out test set v2 ∥ 👤 (start any time, needed before P21)

**Goal:** an honest accuracy number (D9, NFR-01).

| Task | Detail |
| --- | --- |
| P19.1 👤 | You or a teammate write ~30 Indian-style texts **without looking at fusion rules or v1 errors**, in `[[value|TYPE]]` markup, fake data only |
| P19.2 | Cache NER outputs for v2; score rules / NER / baseline / fusion; `docs/results/handwritten-v2.md` with the numbers and limits |
| P19.3 | Any bug found becomes a regression test; **no tuning on v2** (it stays held out) |

- **Files:** `data/eval/handwritten_v2.txt`, `data/eval/ner_cache_v2.jsonl`, `docs/results/handwritten-v2.md`
- **Done when:** the v2 F1 is recorded; PRD success criterion 2 checked (F1 ≥ 0.90, checksum-type precision 1.0)

### P20. Deployment

**Goal:** the public demo runs on the host chosen in D13.

| Task | Detail |
| --- | --- |
| P20.1 👤 | Create the host account/VM per D13; DNS if any |
| P20.2 | Generate 4 production keys into the host's secret store (never in git); set env per API.md 10 |
| P20.3 | Deploy the tagged image with the `/data` volume; HTTPS; health check |
| P20.4 | Schedule daily backups (DATABASE 10.2) to a second location; save the audit anchor off the server (documented process) |
| P20.5 | Production smoke test: J1–J5 on the live URL; headers check; no DEV keys accepted |

- **Files:** `docs/runbook-deploy.md`, deploy config for the chosen host
- **Prerequisites:** P18, D13 answered
- **Done when:** PRD success criteria 1, 4, 5, 6, 9 pass on the live URL

### P21. README and landing page (S0)

**Goal:** what a recruiter sees first (D12).

| Task | Detail |
| --- | --- |
| P21.1 | README: what it is, architecture diagram, how the agent graph works, results (v2 numbers only), how to run, decision log link |
| P21.2 | S0 landing per DESIGN 15: hero with the real S4 screenshot, sections, tagline reveal, FAQ, one action "Try the demo"; real figures only |
| P21.3 | Demo account flow for visitors (a seeded `demo` user via `cli seed-demo`, PRD 14 compatible) |

- **Files:** `README.md`, `frontend/src/pages/Landing.tsx`, `features/landing/*`
- **Prerequisites:** P19, P20
- **Done when:** landing passes the DESIGN.md ship checklist; no invented numbers

### P22. Release

**Goal:** v1.0.0.

| Task | Detail |
| --- | --- |
| P22.1 | Go through PRD success criteria 1–9; record results in `docs/results/release-v1.md` |
| P22.2 👤 | Record the demo video (J1 → J2 → J3 → J4 tamper) |
| P22.3 | Tag `v1.0.0`; close the milestone checklist |

- **Done when:** all 9 PRD success criteria pass and are written down

---

## Out of plan (by design)

Not scheduled because PRD.md section 14 rules them out: OCR, LLM detector, signed reports, multiple organisations, SSO/password reset, Insights screen, developer API keys, Postgres (future swap), SSE (future swap), UPI/landline/ORG detection.

---

## Recommended first task

**P1.1 + P1.2: settings and the four-purpose key ring.** (After P0, merging the docs, which takes minutes once you answer D13–D17.)

Why first: every later phase reads `config.py` and needs `PG_STORAGE_KEY` (P3 file store, P4 checkpoints). It touches only two existing modules, needs no new dependency, and is fully testable on its own.

Scope:
- `config.py`: all runtime variables from API.md 10.1 with types and defaults; in `prod`, refuse missing, short, reused or DEV keys and a missing `PUBLIC_ORIGIN`.
- `keys.py`: add `Purpose.STORAGE` / `PG_STORAGE_KEY`; `KeyRing.dev()` gives 4 distinct keys.
- `.env.example`: the new variables, with comments.
- Tests: `dev` starts with nothing set; each `prod` refusal; 4 distinct dev keys; key bytes never in `repr` or logs.

Done when: all existing 125 tests still pass, the new tests pass, and `python -m app.cli scan …` still works unchanged.

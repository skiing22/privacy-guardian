# AGENTS.md: rules for coding agents

> Every coding agent (and human) working on Privacy Guardian Agent v2 follows these rules. They are short on purpose. When a rule and a request conflict, **stop and ask**; do not pick one silently.

---

## 0. The five rules that matter most

1. **Read before you write.** Inspect the existing code and the relevant doc section before changing anything.
2. **Follow the documents.** They decide what to build; you decide how, inside their rules.
3. **Reuse what exists.** Extend existing modules, interfaces and components; do not build a second version.
4. **Change only what the task needs.** No drive-by refactors, renames, reformatting or "improvements".
5. **Never expose secrets or personal data**: not in code, logs, tests, commits, errors or responses.

---

## 1. Source of truth

### 1.1 Documents and precedence

| Topic | Document | Wins over |
| --- | --- | --- |
| What to build, scope, MVP | `docs/PRD.md` | everything else |
| How it looks and reads | `docs/DESIGN.md` | ARCHITECTURE for UI |
| How it is built | `docs/ARCHITECTURE.md` | SRS |
| Data model | `docs/DATABASE.md` | ARCHITECTURE section 7 |
| API contract | `docs/API.md` | ARCHITECTURE section 9 |
| Why a choice was made | `docs/decisions/` (ADRs) | — (explains, never overrides PRD) |
| Agent rules | `AGENTS.md` (this file) | — |
| Old spec | `docs/SRS.md` | nothing (superseded, kept for history) |

### 1.2 When documents disagree or are silent

- **Disagree:** follow the higher one in the table, then tell the owner and propose a doc fix in the same change.
- **Silent** on something that affects users, data, security or cost: **ask** before building. Do not invent features (PRD rule).
- **Silent** on a small implementation detail: follow the nearest existing pattern in the code.
- Anything listed as **out of scope** in PRD section 14 is not built, even if it is easy.

---

## 2. Working method

### 2.1 Before changing code

1. Read the task and the doc sections it touches (cite them in your summary, e.g. "API.md 4.8").
2. Find the existing code: search for the module, function, type or component first. Read it fully, plus its tests.
3. Run the checks on the current state (section 9.3) so you know what was already passing.
4. If the change is bigger than the task suggests, or touches security, data or the API contract, describe the plan and wait for approval.

### 2.2 While changing code

- Smallest change that solves the task. Keep existing names, structure and style.
- **Bug fix = failing test first**, then the fix. Name the test after the bug.
- One concern per change. If you notice an unrelated problem, **report it**; do not fix it in the same change.
- Never delete or weaken a test, a type check or a lint rule to make something pass. If a test is wrong, say why and fix it openly.

### 2.3 After changing code

- Run every check in section 9.3. All must pass.
- If detection, fusion, policy or the graph changed: re-run the eval (`ml/scripts/eval_handwritten.py --ner-cache …`) and report the before/after F1. A drop needs an explanation.
- Update the docs your change affects (section 10).
- Summarise: what changed, why, which files, test results, anything left open. No step-by-step diary.

### 2.4 Delivering changes

- With push access: a branch and a pull request (section 11).
- **Without push access:** deliver a zip of **only the changed and new files**, at their repo paths, built from an up-to-date `main`. Before sending, check every file in the zip against `origin/main` and list them. A merge that misses files breaks CI (this happened in PR #10).

---

## 3. Project structure

The layout is fixed by ARCHITECTURE section 6. Put code where it belongs; do not create new top-level folders.

### 3.1 Backend layers

| Layer | Folder | May import |
| --- | --- | --- |
| API | `backend/app/api/` | services, schemas |
| Services | `backend/app/services/` | domain, storage |
| Domain | `backend/app/{detectors,fusion,policy,graph,crypto,parsers}/` | other domain modules only |
| Storage | `backend/app/storage/` | domain interfaces |
| Runtime | `backend/app/runtime/` | services |

- **Domain code never imports `api`, `services`, `storage`, FastAPI or SQLAlchemy.** CI checks this.
- New storage goes behind the domain's existing interfaces (`BeliefStore`, `TokenRegistry`, `VaultStore`, `AuditStore`). Do not add a parallel interface.
- The CLI (`app/cli.py`) uses services and domain code, never raw SQL.

### 3.2 Frontend

Folders per ARCHITECTURE 4.1: `app/`, `pages/` (one per screen), `features/`, `ui/`, `api/`, `styles/`. A file goes in `ui/` only if DESIGN.md section 5 defines it.

### 3.3 Other folders

- `ml/`: training and evaluation only; the app never imports from it.
- `data/eval`, `data/samples`: fake data only. Runtime data lives in `DATA_DIR`, never in the repo.
- `docs/`: documents, ADRs, results.

---

## 4. Code quality and naming

### 4.1 General

- Readable over clever. Functions do one thing; most are under 40 lines.
- Comments explain **why**, not what. Each module starts with a short docstring saying what it is for and which FR/ADR it serves (follow existing modules).
- No dead code, commented-out code, `print` debugging or TODOs without an issue link.
- No magic numbers: named constants at the top of the module, with a comment on where the value comes from (see `fusion/risk.py`, `policy/actions.py`).

### 4.2 Python

| Thing | Rule | Example in repo |
| --- | --- | --- |
| Modules, functions, variables | `snake_case` | `fuse.py`, `filter_known` |
| Classes | `PascalCase` | `RuleDetector`, `AuditLog` |
| Exceptions | `PascalCase`, end in `Error` | `ParseError`, `AccessDeniedError` |
| Constants | `UPPER_SNAKE` | `MAX_BYTES`, `GENESIS` |
| Enums | `StrEnum` with values matching DATABASE.md | `PiiType`, `Action` |
| Value objects | `@dataclass(frozen=True)` | `Span`, `Decision` |
| Interfaces | `typing.Protocol` | `BeliefStore`, `Detector` |
| Private helpers | leading `_` | `_clusters`, `_aad` |

Line length 100 (ruff). Format with `ruff format`; never hand-format against it.

### 4.3 TypeScript / React

| Thing | Rule |
| --- | --- |
| Components, types | `PascalCase` (`ReviewCard`, `ScanStatus`) |
| Hooks | `useXxx` (`useScan`, `useAuditLog`) |
| Files | Component files named after the component; one component per file |
| Props | A named `Props` type per component; no prop spreading of unknown objects |
| Copy | Sentence case; words from DESIGN.md section 13; no hyphens in sentences; no exclamation marks |

---

## 5. Component and pattern reuse

### 5.1 Backend

- Before writing a helper, search for it. Existing ones to reuse: `normalize()` for canonical values, `fuse()` for combining spans, `link()` for entities, `assess()` for risk, `allowed()`/`render()` for actions, `canonical()` for stable JSON, `ParsedDoc.locate()` for offsets.
- New detectors implement the existing `Detector` protocol (`detect(text) -> list[Span]`) and are added to the graph's detector map; nothing else changes.
- New PII types: add to `PiiType`, the label map, priors, families in DESIGN.md, the SQL enum (migration) and the enum-sync test, in one change.

### 5.2 Frontend

- Use the components in `ui/` (DESIGN.md 5). If a screen needs something new, first try to compose existing ones; if it is truly new, add it to DESIGN.md and `ui/` in the same change.
- **Tokens only:** colours, sizes, spacing and radius come from the Tailwind theme built from DESIGN.md. No raw hex, no arbitrary values like `text-[19px]` or `p-[13px]`.
- One button pair, one panel style, one link look. No new variants without a DESIGN.md change.
- Icons: Phosphor only. No emoji in the UI.
- Masking, tokens and generalized values are rendered from the API's `output` field; never re-implement them in the frontend.

---

## 6. Dependencies

- **Default answer is no.** Use the standard library or an existing dependency first.
- A new dependency needs, in the pull request: why it is needed, what was considered, its licence (must allow use and distribution; no GPL in the app), maintenance status, and size. A dependency that changes the architecture (a new service, framework or database) needs an ADR first.
- Never add a dependency for a few lines of code.
- Pin versions: backend ranges in `pyproject.toml` with an upper bound for fast-moving libraries (e.g. `langgraph>=1.2,<2`); exact versions in the lockfiles; frontend through `package-lock.json`.
- Not allowed in the app: external API clients for runtime calls (API.md 8.1), analytics, CDN-hosted assets, component libraries (DESIGN.md 5), state libraries besides TanStack Query (ARCHITECTURE 1.2).
- Heavy ML packages stay in the `ml` extra; CI's core job must run without PyTorch.

---

## 7. Type safety

### 7.1 Python

- `mypy --strict` passes on `app/`. Every function has typed parameters and return type.
- No `Any` in domain code. In API/storage code, `Any` only at a library boundary, with a comment.
- `# type: ignore` only with the specific error code and a reason comment (e.g. `# type: ignore[import-not-found]  # transformers loaded lazily`).
- Request and response bodies are Pydantic models; never pass raw `dict`s between layers.
- Enums, not bare strings, for anything with a fixed set of values.

### 7.2 TypeScript

- `strict: true`. No `any`, no `@ts-ignore`; use `unknown` and narrow it.
- API types are **generated** from the backend OpenAPI schema; never hand-written. If a type is wrong, fix the backend schema.
- Server data enters the app only through `api/` hooks.

---

## 8. Error handling

- Follow ARCHITECTURE 13 and API.md 2.3 to 2.4.
- **Domain** raises specific exceptions (`ParseError`, `VaultError`, …). **Services** turn them into app errors with a `code` from API.md 2.4. **API** maps codes to HTTP status and the standard error body. Do not invent new codes without adding them to API.md.
- Never swallow an exception. `except Exception` only at the top of the worker loop and the API's global handler, and it must log and set a failed state.
- Error messages shown to users come from the API.md table: specific, calm, no apologies, never containing document text, values, SQL or stack traces.
- The worker never lets one bad scan stop the queue: mark it `failed` with `error_code` and `step`, keep its checkpoint, continue.
- Fail closed on security: if an audit write fails, the action fails (no value revealed, no scan finished unlogged).

---

## 9. Testing

### 9.1 What every change needs

| Change | Required tests |
| --- | --- |
| Bug fix | A test that fails before the fix and passes after, named after the bug |
| New domain function | Unit tests for normal, edge and error cases; a Hypothesis property test for algorithms (merging, chunking, tokens, chains) |
| New store implementation | The **same** test suite the in-memory store passes |
| New endpoint | Happy path, every error code it can return, and the authorization matrix (owner, other user, admin, logged out) |
| Schema change | Migration upgrades an empty database and the previous head; downgrade works; enum-sync test still passes |
| UI component | Vitest for logic (rendering marks from offsets, keyboard handling); Playwright for the three journeys in ARCHITECTURE 15 when they are touched |
| Detection, fusion or policy change | Eval re-run with before/after numbers |

### 9.2 Test rules

- **Fake data only.** Use made-up names and the generators for valid fake IDs (Verhoeff Aadhaar, Luhn cards). Never real people's data, never data copied from real documents.
- Tests do not need the NER model, the network or a GPU: use the fake detectors pattern from `tests/test_graph.py` and the NER cache for eval.
- No sleeping in tests; inject clocks (see `AuditLog(clock=...)`).
- Tests are independent: temporary directories and databases per test.
- Privacy tests stay green: no sample value in logs, audit payloads or error messages.

### 9.3 Checks that must pass before any change is done

Backend (from `backend/`): `ruff check .` · `ruff format --check .` · `mypy app` · `pytest --cov=app` (coverage ≥ 70%, currently 96%; do not let it drop without a reason) · layer-import check · Alembic upgrade on an empty database.
Frontend (from `frontend/`): type check · lint · Vitest · production build.
Docker build must succeed.

---

## 10. Documentation

| When you… | Update |
| --- | --- |
| Make a design or technology choice that someone could reasonably question | A new ADR in `docs/decisions/` (use `template.md`) + a row in its README. Never edit an old ADR's decision; supersede it with a new one |
| Change scope or behaviour users see | `docs/PRD.md` (only with owner approval) |
| Add or change a screen, component, colour, wording | `docs/DESIGN.md` |
| Change tables, columns, constraints, retention | `docs/DATABASE.md` + migration |
| Change an endpoint, field, error code, limit | `docs/API.md` |
| Change structure, stack, deployment, env vars | `docs/ARCHITECTURE.md` + `.env.example` |
| Measure accuracy or performance | A file in `docs/results/` with the date, data set, command and numbers |
| Finish a checklist item | The milestone checklist |

- Docs change in the **same** change as the code they describe.
- Results are reported honestly: include the data set and its limits (e.g. "v1 set was used to design the rules, so this is optimistic"). No accuracy claim in the README until the held-out set v2 is scored (D9).

---

## 11. Git and change discipline

- **Never commit to `main`.** Branch per change: `feature/…`, `fix/…`, `docs/…`, `chore/…`.
- **Conventional Commits** with requirement ids: `feat(graph): verifier loop (FR-21)`, `fix(rules): leading 0 phone numbers`, `docs: API.md`.
- One logical change per commit; one concern per pull request. Pull request description says what, why, which docs/ADRs, test results, and anything not done.
- Merge only with green required checks (`backend`, `docker`, and `frontend` once it exists). Never bypass branch protection; never force-push to `main`.
- Tag each finished milestone: `v0.N.0`.
- Never commit: `.env`, keys, model weights, `data/raw/`, runtime data (`data/*.json`, `audit.jsonl`, databases), generated folders (`node_modules`, `dist`, caches), or any real personal data. Check `git status` before every commit.
- No unrelated changes: no reformatting of untouched files, no dependency bumps, no renames, no lockfile churn unless the task is about them.

---

## 12. Security and secrets

### 12.1 Secrets

- Secrets live only in environment variables (API.md 10). Never in code, tests, docs, commits, logs, error messages, the frontend bundle or Docker image layers.
- `HF_TOKEN` is a Docker **build secret**, never a build arg or env var in the image.
- `KeySet.__repr__` must never print key bytes; keep it that way for any new secret-holding type.
- DEV keys (`KeyRing.dev()`) are for local runs and tests only; `prod` refuses them.
- If a secret is ever committed: stop, tell the owner, rotate it (append a new key id), then remove it from history. Deleting the line is not enough.

### 12.2 Personal data

- The rules in DATABASE.md section 7 and API.md section 11 are mandatory: no raw values in plaintext columns, logs, URLs, audit payloads, reports, error messages or filenames we generate.
- Only three endpoints return document content (API.md 11). Adding a fourth needs owner approval and a doc update.
- Real values come back only through `Vault.reidentify`, which checks role and reason and audits first. Do not add another path.
- No runtime outbound network calls (API.md 8.1). Do not add telemetry, error-reporting services or remote fonts.

### 12.3 Crypto

- Use the existing `app/crypto/` modules and the `cryptography` library. **Never write your own primitives**, never use ECB, never reuse a GCM nonce, never use `random` for secrets (use `secrets`/`os.urandom`).
- Compare MACs and tokens with `hmac.compare_digest`.
- Any change to token, vault or audit formats needs an ADR and must keep old data verifiable (key ids, rotation).

### 12.4 Input

- All input is untrusted: validate at the API boundary (types, sizes, formats), then again where a rule matters (service/domain).
- Files: size limit while streaming, extension **and** magic bytes, DOCX zip-bomb check, parse timeout (API.md 4.5).
- Render document text as text, never as HTML. No `dangerouslySetInnerHTML`.

---

## 13. Database and API access

### 13.1 Database

- Only `app/storage/` imports SQLAlchemy or runs SQL. Services call repositories; repositories return domain objects, not ORM rows.
- **Every** query on `scans`, `scan_files` or `decisions` from API code is scoped by `owner_id`. The unscoped worker and retention repositories live in a separate module that API code must not import (DATABASE 8).
- Every schema change is an Alembic migration plus a DATABASE.md update, in one change. Never edit a migration that has been merged.
- Writes that belong together use one transaction in the service. Audit appends use `BEGIN IMMEDIATE`.
- `audit_log` is append-only; never write an UPDATE or DELETE for it, and never drop its triggers.
- Use bound parameters only; never build SQL with string formatting.
- Add an index only for a real query, and note the query in DATABASE.md section 6.

### 13.2 API

- Endpoints, fields, status codes and error codes exactly as in API.md. A new or changed endpoint updates API.md in the same change; the regenerated frontend types must still compile.
- Authorization is enforced on the server by router dependencies and scoped queries; hiding a button in the UI is never protection.
- Other users' resources return **404**, not 403.
- Every API response gets the headers in API.md 2.2, including `Cache-Control: no-store`.
- Keep conventions: `snake_case` fields, UTC ISO times, `null` instead of missing fields, unknown fields rejected, cursor pagination.

---

## 14. Definition of done

A change is done only when all of these are true:

- [ ] It does what the task asked, nothing more, and follows the relevant doc sections.
- [ ] Existing code and patterns were reused; no duplicate helpers, components or interfaces.
- [ ] No new dependency, or one justified as in section 6.
- [ ] All checks in 9.3 pass; required new tests exist; coverage did not drop without a reason.
- [ ] Eval re-run if detection, fusion, policy or the graph changed.
- [ ] No secrets or personal data anywhere in the diff, logs or test output.
- [ ] Docs, ADRs and `.env.example` updated where affected.
- [ ] Commit messages follow section 11; the branch contains every changed file.
- [ ] The summary lists what changed, test results, and anything left open.

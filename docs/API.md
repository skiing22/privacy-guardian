# API: Privacy Guardian Agent v2

> How the app talks to itself and to the outside world. Sources of truth: **PRD.md**, **ARCHITECTURE.md**, **DATABASE.md**. This file **refines ARCHITECTURE.md section 9**; where they differ, this file wins for anything about the API.
>
> Uses ARCHITECTURE decisions **D14** (session cookies), **D15** (`PG_STORAGE_KEY`), **D16** (model in a private Hugging Face repo) and **D17** (one worker thread), approved in ADR-0022.

---

## 1. Overview

| Interface | Between | Style |
| --- | --- | --- |
| **Public HTTP API** | Browser (React app) ↔ backend | REST + JSON over HTTPS, same origin, under `/api/v1` |
| **Health** | Host / Docker ↔ backend | `GET /health` |
| **Internal** | API ↔ scan worker ↔ graph ↔ storage | In-process function calls and one in-memory queue. **No internal HTTP** |
| **External** | Build pipeline ↔ Hugging Face Hub | One download of the model weights at **image build time only** |

At runtime the app makes **no outbound network calls**. Documents and their contents never leave the server.

**19 endpoints** exist: 1 health, 3 auth, 8 scan, 7 admin. Nothing is exposed that a screen in PRD section 8 does not use.

---

## 2. Conventions

### 2.1 Basics

| Item | Rule |
| --- | --- |
| Base path | `/api/v1` (version in the path; a breaking change means `/api/v2`) |
| Content type | Requests: `application/json`, or `multipart/form-data` for uploads only. Responses: `application/json`, except downloads |
| Field names | `snake_case`, matching the database and Python code |
| Times | UTC ISO 8601 with `Z`, e.g. `2026-11-19T01:01:12.345Z` |
| IDs | Scans: UUID v4. Users: integer. Audit: integer `seq` |
| Enums | Same values as DATABASE.md 1.2 (`pii_type`, `action`, `scan_status`, `risk_level`, `role`) |
| Empty values | Field present with `null`, never omitted, so the client's types stay simple |
| Unknown fields | Rejected with `422 invalid_request` (catches client bugs and typos) |
| Success codes | `200` read or synchronous result · `202` accepted for background work · `204` done, no body |
| Contract | FastAPI's OpenAPI schema is the contract; frontend types are generated from it in CI. `/docs` is on in `dev`, off in `prod` |

### 2.2 Headers on every API response

| Header | Value | Why |
| --- | --- | --- |
| `X-Request-ID` | UUID (echoes a client-sent one if valid) | Ties a user's error report to server logs |
| `Cache-Control` | `no-store` | Responses may contain personal data; browsers and proxies must not keep them |
| `Content-Security-Policy` | `default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'` | ARCHITECTURE 14.2 |
| `X-Content-Type-Options` | `nosniff` | |
| `Referrer-Policy` | `no-referrer` | |
| `Strict-Transport-Security` | `max-age=31536000` (prod) | |

### 2.3 Error format

Every non-2xx response has this body:

```json
{
  "error": {
    "code": "reason_too_short",
    "message": "Reason must be at least 10 characters.",
    "field": "reason",
    "request_id": "6b1f0c7e-2c8a-4f53-9d0e-0a6f2b3c4d5e"
  }
}
```

- `code`: stable, machine-readable; the frontend switches on it.
- `message`: safe to show as is; wording follows PRD section 12 and DESIGN section 13.
- `field`: the input field at fault, or `null`.
- **Messages never contain document text, item values, filenames of other users, stack traces or SQL.**

### 2.4 Error codes

| HTTP | `code` | When | Message shown |
| --- | --- | --- | --- |
| 400 | `bad_origin` | State-changing request from another origin | "Request blocked." |
| 401 | `auth_required` | No valid session | "Please log in." |
| 401 | `auth_failed` | Wrong email or password (same for both) | "Wrong email or password." |
| 401 | `session_expired` | Session past its expiry | "Please log in again." |
| 403 | `forbidden` | Logged in, wrong role | "Only admins can do this." |
| 404 | `not_found` | Missing, or belongs to someone else | "Not found." |
| 409 | `not_waiting_for_review` | Answers sent when the scan is not paused | "This scan is not waiting for answers." |
| 409 | `scan_not_done` | Result or download before `done` | "This scan has not finished yet." |
| 409 | `scan_running` | Delete or retry while `queued`/`running` | "This scan is still running." |
| 409 | `scan_not_failed` | Retry on a scan that did not fail | "Only failed scans can be retried." |
| 413 | `file_too_large` | Over `MAX_UPLOAD_MB` | "File too large (max 10 MB)." |
| 415 | `unsupported_type` | Not TXT, MD, PDF, DOCX or CSV, or contents do not match the extension | "Only TXT, PDF, DOCX and CSV files are supported." |
| 422 | `invalid_request` | Schema error, unknown field, wrong type | Field-specific text |
| 422 | `empty_input` | No file and no text, or both | "Add a file or paste some text." |
| 422 | `pdf_no_text` | PDF without a text layer | "This PDF has no text (scanned image). Not supported yet." |
| 422 | `file_unreadable` | Broken file, zip bomb, parse timeout | "This file could not be read." |
| 422 | `invalid_answers` | Missing, duplicate or out-of-range answers | "Answer every item once." |
| 422 | `action_not_allowed` | Rule action that does not fit the type | "That action is not available for this type." |
| 422 | `reason_too_short` | Reveal reason under 10 characters | "Reason must be at least 10 characters." |
| 404 | `unknown_token` | Reveal of a token not in the vault (or already deleted) | "Unknown token." |
| 422 | `vault_integrity` | Vault entry failed its integrity check | "Vault entry failed integrity check." |
| 429 | `rate_limited` | Section 7 limits | "Too many tries. Wait {n} seconds." |
| 503 | `model_not_ready` | Only for `/health` readiness | "Preparing the model." |
| 503 | `busy` | Database stayed locked after one retry | "Service busy. Try again shortly." |
| 503 | `storage_unavailable` | Disk full or not writable | "Service unavailable. Try again shortly." |
| 500 | `internal` | Anything unexpected | "Something went wrong. Quote request {request_id}." |

---

## 3. Authentication and authorization

### 3.1 Sessions

- `POST /auth/login` sets a cookie `pg_session`: 32 random bytes, `HttpOnly`, `Secure` (prod), `SameSite=Strict`, `Path=/`. The database stores only its SHA-256 (DATABASE 3.2).
- Every other `/api/v1` route needs a valid session. The cookie is **never** readable by JavaScript and never sent in a URL or body.
- Lifetime: 8 hours idle, 7 days total. `POST /auth/logout` deletes it server-side.
- No tokens, keys or secrets are ever sent to the browser. The frontend build contains **no** environment secrets.

### 3.2 Cross-site protection

- `SameSite=Strict` cookie.
- Every `POST`, `PUT` and `DELETE` must carry an `Origin` header equal to `PUBLIC_ORIGIN`; otherwise `400 bad_origin`.
- No CORS headers are sent: the API is same-origin only.

### 3.3 Authorization (always server-side)

| Level | Rule | Enforced by |
| --- | --- | --- |
| Public | `/health`, `POST /auth/login` | Route config |
| User | Valid session and `is_active = 1` | Auth dependency on the router |
| Owner | Scan routes act only on scans where `owner_id` = current user; anything else returns **404** (never 403, so scan ids cannot be probed) | Storage layer: every scan query is scoped by owner (DATABASE 8) |
| Admin | `role = 'admin'` for every `/admin/*` route | Router dependency **and** domain checks (reveal re-checks role and reason) |

Client-side role checks (hiding admin links) are for convenience only and are never trusted.

---

## 4. Endpoints

All paths below are under `/api/v1` except `/health`.

| # | Method | Path | Access | Purpose | Screen |
| --- | --- | --- | --- | --- | --- |
| 1 | GET | `/health` | public | Liveness and model readiness | Host |
| 2 | POST | `/auth/login` | public | Start a session | S1 |
| 3 | POST | `/auth/logout` | user | End the session | All |
| 4 | GET | `/auth/me` | user | Who am I, my role | All |
| 5 | POST | `/scans` | user | Upload a file or text and start a scan | S3 |
| 6 | GET | `/scans` | user | My scans, newest first | S2 |
| 7 | GET | `/scans/{id}` | owner | Status, progress, review items, risk | S4 (polled) |
| 8 | POST | `/scans/{id}/answers` | owner | Submit review answers and resume | S4 |
| 9 | GET | `/scans/{id}/result` | owner | Texts, items, decisions, risk for the result view | S4 |
| 10 | GET | `/scans/{id}/download` | owner | Cleaned file or JSON report | S4 |
| 11 | POST | `/scans/{id}/retry` | owner | Run a failed scan again | S4 |
| 12 | DELETE | `/scans/{id}` | owner | Delete scan, files and unused vault entries now | S2, S4 |
| 13 | GET | `/admin/rules` | admin | Fixed action per PII type | S5 |
| 14 | PUT | `/admin/rules` | admin | Save fixed actions | S5 |
| 15 | POST | `/admin/reveal` | admin | Token + reason → real value (logged) | S5 |
| 16 | POST | `/admin/beliefs/reset` | admin | Reset learned beliefs to priors | S5 |
| 17 | GET | `/admin/audit` | admin | Audit events, newest first | S6 |
| 18 | POST | `/admin/audit/verify` | admin | Verify the chain against the anchor | S6 |
| 19 | POST | `/admin/audit/anchor` | admin | Save the current anchor | S6 |

The same app also serves the frontend's static files at `/*`; that is not part of the API.

Not provided on purpose: sign-up, password reset, user management (CLI only, PRD 9), beliefs read-out (Insights cut), developer API keys (PRD 14).

---

### 4.1 `GET /health`

Public. Used by the host and by the frontend to show "Preparing the model".

`200`
```json
{ "status": "ok", "model_ready": true, "version": "0.6.0" }
```
While the model loads: `503` with `{ "status": "starting", "model_ready": false, "version": "…", "error": { "code": "model_not_ready", … } }`. Never reveals keys, paths or config.

### 4.2 `POST /auth/login`

```json
{ "email": "rahul@example.com", "password": "••••••••" }
```
| Field | Rules |
| --- | --- |
| `email` | 3–254 chars, contains `@`, trimmed, compared case-insensitively |
| `password` | 8–128 chars |

`204` + `Set-Cookie`. Errors: `401 auth_failed` (also for disabled accounts), `429 rate_limited`, `422 invalid_request`. Writes no audit record (audit is for data actions; login attempts go to app logs without the password).

### 4.3 `POST /auth/logout`

`204`, cookie cleared, session row deleted. Idempotent.

### 4.4 `GET /auth/me`

`200`
```json
{ "id": 12, "email": "rahul@example.com", "role": "user" }
```
`401 auth_required` or `401 session_expired` otherwise; the frontend sends the user to `/login?next=…`.

### 4.5 `POST /scans`

`multipart/form-data` with **exactly one** of:

| Part | Rules |
| --- | --- |
| `file` | ≤ `MAX_UPLOAD_MB` (checked while streaming, stops reading at the limit); extension `.txt .md .pdf .docx .csv`; first bytes must match (`%PDF-` for PDF, a ZIP header for DOCX, valid UTF-8 or CP-1252 text for the rest); DOCX total uncompressed size ≤ 50 MB |
| `text` | 1–200,000 characters after trimming; stored as `pasted-text.txt` |

`202`
```json
{
  "id": "3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90",
  "status": "queued",
  "poll_url": "/api/v1/scans/3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90"
}
```
Errors: `413 file_too_large`, `415 unsupported_type`, `422 empty_input`, `429 rate_limited`, `503 storage_unavailable`.
Deep checks (PDF text layer, readable DOCX) happen in the worker; failures there end the scan as `failed` with `pdf_no_text` or `file_unreadable`.

### 4.6 `GET /scans`

Query: `status` (optional, one `scan_status`), `limit` (1–100, default 50), `cursor` (opaque).
Order: newest first. S2 shows "Needs review" first by calling once with `status=needs_review` and once without (DESIGN 12).

`200`
```json
{
  "items": [
    {
      "id": "3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90",
      "filename": "patient_note.txt",
      "format": "txt",
      "status": "done",
      "risk_level": "LOW",
      "created_at": "2026-11-18T23:52:04.120Z",
      "expires_at": "2026-11-25T23:52:04.120Z"
    }
  ],
  "next_cursor": null
}
```

### 4.7 `GET /scans/{id}` (polled)

The cheap status read the frontend polls every 1 s while `queued` or `running` (section 5).

`200`
```json
{
  "id": "3f2a9c1e-…",
  "filename": "patient_note.txt",
  "format": "txt",
  "status": "needs_review",
  "step": 3,
  "step_label": "Combining results",
  "round": 1,
  "max_rounds": 3,
  "created_at": "…", "updated_at": "…", "finished_at": null, "expires_at": "…",
  "review": {
    "items": [
      {
        "index": 4,
        "pii_type": "ADDRESS",
        "family": "contact",
        "score": 0.58,
        "reason": "low confidence",
        "context": { "before": "…send the documents to ", "text": "22, Nehru Nagar", "after": ", Bhopal 462003…" }
      }
    ]
  },
  "risk": null,
  "error": null
}
```
- `review` is non-null only when `status = needs_review`. `context` is at most 60 characters on each side and is the only place this endpoint returns document text (owner only, `no-store`).
- `risk` is non-null only when `done`: `{ "level": "LOW", "est_matches": 1750.0, "clues": ["gender","age_range","birth_year"], "unresolved_leaks": 0 }`.
- `error` is non-null only when `failed`: `{ "code": "pdf_no_text", "message": "…", "step": 1 }`.
- `step_label` values (DESIGN 5.7): `Reading file`, `Finding personal data`, `Combining results`, `Choosing what to hide`, `Checking for leaks`.

### 4.8 `POST /scans/{id}/answers`

```json
{
  "answers": [
    { "index": 4, "verdict": "protect" },
    { "index": 7, "verdict": "not_pii" },
    { "index": 9, "verdict": "keep", "pii_type": null }
  ]
}
```
| Rule | Detail |
| --- | --- |
| `verdict` | `protect`, `keep`, `not_pii` (DESIGN wording: Protect / Keep visible / Not personal data) |
| `pii_type` | Optional correction of the type; must be a `pii_type` |
| Completeness | Every pending `index` answered exactly once; no other indexes |

`202 { "id": "…", "status": "queued" }`. The worker resumes the paused graph, updates beliefs and writes a `review` audit record (types and verdicts only).
Errors: `409 not_waiting_for_review`, `422 invalid_answers`, `404 not_found`.
**Idempotency:** a second identical submit after the first was accepted returns `409 not_waiting_for_review`; the client treats that as success if the scan has moved on.

### 4.9 `GET /scans/{id}/result`

Everything S4 needs to draw the original and cleaned sheets and the item list. Built from the encrypted original + `decisions`; nothing is stored twice (DATABASE 2.1).

`200`
```json
{
  "id": "3f2a9c1e-…",
  "rounds": 1,
  "risk": { "level": "LOW", "est_matches": 1750.0, "clues": ["gender","age_range"], "unresolved_leaks": 0 },
  "original_text": "Discharge summary - Sunrise Hospital, Kozhikode\nPatient: Arjun Nair, Male, age 34. …",
  "items": [
    {
      "idx": 2, "round": 1, "start": 56, "end": 66,
      "pii_type": "PERSON", "family": "identity", "score": 0.97, "sources": ["ner"],
      "action": "pseudonymize", "action_label": "Replace with token",
      "reason": "utility", "reason_text": "Names are sensitive by default.",
      "token": "PERSON_c97ab2", "output": "PERSON_c97ab2"
    }
  ],
  "cleaned_segments": [
    { "text": "Discharge summary - ", "item_idx": null },
    { "text": "LOCATION_553c17", "item_idx": 0 },
    { "text": " Hospital, ", "item_idx": null }
  ]
}
```
- `items[*].start/end` refer to `original_text` for round 1. Items found in later rounds are shown in `cleaned_segments` only (they never existed in the original).
- `output` is the exact replacement text (token, mask, generalized value or `[REDACTED]`), so the frontend never re-implements masking.
- `cleaned_segments` joined together equal the cleaned text exactly; the frontend renders marks from `item_idx`.
- Errors: `409 scan_not_done`, `404 not_found`.

### 4.10 `GET /scans/{id}/download?kind=cleaned|report`

| `kind` | Returns | `Content-Type` |
| --- | --- | --- |
| `cleaned` | The cleaned file in the input's format; PDF input returns `.txt` (D4) | Per format |
| `report` | JSON report (below) | `application/json` |

Headers: `Content-Disposition: attachment; filename="cleaned-3f2a9c1e.docx"` (scan id, not the original name, so a name inside the filename is not copied around), `Cache-Control: no-store`.

Report body (no real values, ever):
```json
{
  "report_version": 1,
  "scan_id": "3f2a9c1e-…",
  "model_version": "a41c07be92d1",
  "created_at": "…", "finished_at": "…",
  "rounds": 1,
  "risk": { "level": "LOW", "est_matches": 1750.0, "clues": ["gender","age_range"], "unresolved_leaks": 0 },
  "counts": { "PERSON:pseudonymize": 4, "AGE:generalize": 1 },
  "items": [ { "idx": 2, "round": 1, "start": 56, "end": 66, "pii_type": "PERSON", "action": "pseudonymize", "reason": "utility", "token": "PERSON_c97ab2" } ]
}
```
Errors: `409 scan_not_done`, `404 not_found`, `422 invalid_request` (bad `kind`).

### 4.11 `POST /scans/{id}/retry`

No body. Re-queues a `failed` scan; it resumes from its last checkpoint if one exists, else starts again from the original file.
`202 { "id": "…", "status": "queued" }`. Errors: `409 scan_not_failed`, `404 not_found`.

### 4.12 `DELETE /scans/{id}`

`204`. Deletes the scan row (cascading to files and decisions), its files and checkpoints, and vault rows no other scan uses (DATABASE 10.3). Errors: `409 scan_running`, `404 not_found`. Deleting an already deleted scan returns `404`.

### 4.13 `GET /admin/rules`

`200`
```json
{
  "rules": [
    { "pii_type": "AADHAAR", "family": "id", "action": "redact", "allowed_actions": ["keep","mask","pseudonymize","redact"], "updated_at": "…" },
    { "pii_type": "AGE", "family": "identity", "action": null, "allowed_actions": ["keep","generalize","redact"], "updated_at": null }
  ]
}
```
All 15 types are always listed; `action: null` = Automatic.

### 4.14 `PUT /admin/rules`

Full replacement of the fixed rules (simpler than partial updates; the list is small).
```json
{ "rules": [ { "pii_type": "AADHAAR", "action": "redact" }, { "pii_type": "AGE", "action": null } ] }
```
Each type at most once; types left out become Automatic. Each action must be in that type's `allowed_actions`.
`200` with the same body as 4.13. Writes `rules_changed` to the audit log (types and actions only). Errors: `422 action_not_allowed`, `422 invalid_request`.

### 4.15 `POST /admin/reveal`

The token and reason go in the body, never in the URL, so they do not land in access logs or browser history.
```json
{ "token": "PERSON_c97ab2", "reason": "court order 2026/77" }
```
| Field | Rules |
| --- | --- |
| `token` | Matches `^[A-Z_]+_[0-9a-f]{6,64}$` |
| `reason` | 10–500 characters, trimmed |

`200`
```json
{ "token": "PERSON_c97ab2", "pii_type": "PERSON", "value": "Arjun Nair", "logged_as": 214 }
```
- The audit record is written **before** the value is returned; if writing it fails, the request fails (`503`) and no value is sent.
- A non-admin call is refused with `403 forbidden` **and** logged as `reidentify_denied`.
- Errors: `404 unknown_token`, `422 reason_too_short`, `422 vault_integrity`, `429 rate_limited`.

### 4.16 `POST /admin/beliefs/reset`

```json
{ "confirm": true }
```
`204`. Deletes all `beliefs` rows (priors apply again) and writes `beliefs_reset` to the audit log.

### 4.17 `GET /admin/audit`

Query: `limit` (1–200, default 50), `before_seq` (optional; returns records with `seq` lower than it).

`200`
```json
{
  "items": [
    {
      "seq": 214,
      "ts": "2026-11-18T23:55:10.002Z",
      "actor": { "type": "user", "id": 3, "email": "admin1@example.com" },
      "event": "reidentify",
      "event_label": "Real value shown",
      "details": { "token": "PERSON_c97ab2", "reason": "court order 2026/77" }
    }
  ],
  "next_before_seq": 164
}
```
`actor.type` is `user` or `system`. `details` is the stored payload, which never holds raw values or filenames (DATABASE 7.2).

### 4.18 `POST /admin/audit/verify`

No body. `200` whether or not tampering is found (the request succeeded; the result is data).
```json
{ "ok": false, "checked": 0, "first_bad_seq": 0, "reason": "payload changed", "anchor": { "seq": 213, "saved_at": "…" } }
```
`anchor` is `null` if none was ever saved.

### 4.19 `POST /admin/audit/anchor`

No body. `200 { "seq": 214, "mac_prefix": "c7cb09bfaec30f24", "saved_at": "…" }`. Writes `anchor_saved` to the audit log first, then anchors that newest record. Only a prefix of the MAC is returned; the full anchor stays server-side.

---

## 5. Pagination, filtering and polling

| List | Style | Default / max | Order | Filters |
| --- | --- | --- | --- | --- |
| `GET /scans` | Opaque `cursor` (encodes the last `created_at` + `id`) | 50 / 100 | Newest first | `status` |
| `GET /admin/audit` | `before_seq` | 50 / 200 | Newest first | None in MVP |

Cursor rules: opaque to the client; an invalid cursor returns `422 invalid_request`; `next_cursor: null` means the end.

**Polling `GET /scans/{id}`** (D6):
- Every 1 s while `queued` or `running`; every 5 s while the tab is hidden; stop on `needs_review`, `done` or `failed`.
- The response is one primary-key read; it is exempt from the general rate limit while the scan is open.
- After `done`, the client fetches `/result` once.

---

## 6. Internal interfaces

Not HTTP; documented so the boundaries stay clean (ARCHITECTURE 3).

| From → To | Contract | Failure behaviour |
| --- | --- | --- |
| API → services | Typed function calls with Pydantic-validated input | Services raise app errors with a `code`; the API maps them (section 2.4) |
| Services → scan worker | `enqueue(scan_id)` on an in-memory FIFO queue; the scan row is the source of truth | If the process dies, startup re-enqueues every `queued`/`running` scan from the database |
| Worker → graph | `start_scan` / `resume_scan` with `thread_id = scan_id`; review answers passed as the resume value | Any exception: scan becomes `failed` with `error_code` and `step`; checkpoint kept so `retry` can resume |
| Worker → scan row | After each node: `step`, `round`, `updated_at` | Write errors retried once, then the scan fails with `busy` |
| Graph → crypto | `Pseudonymizer.token`, `Vault.put`, `AuditLog.append` | Audit append is in the same transaction as the scan's final write; if it fails, the scan fails (no unlogged results) |
| Services → storage | Repository methods; scan methods always take `owner_id` (DATABASE 8) | SQLite busy: one retry after 100 ms, then `503 busy` |

---

## 7. Rate limiting

In-memory counters in the single process (ARCHITECTURE 8.1). Exceeding a limit returns `429 rate_limited` with a `Retry-After` header in seconds.

| Scope | Key | Limit | Why |
| --- | --- | --- | --- |
| Login | email + client IP | 5 failed tries / 5 min, then 60 s lockout | Password guessing |
| Login | client IP | 30 tries / 5 min | Spraying many emails |
| New scans | user | 20 / hour and at most 3 open (`queued`/`running`/`needs_review`) | One worker; protects the queue |
| Reveal | admin user | 10 / hour | Limits damage of a stolen admin session; every attempt is audited anyway |
| Everything else | session | 120 requests / min (status polling exempt while its scan is open) | General abuse |

Counters reset on restart; this is accepted for one process (ARCHITECTURE 14.3). Client IP comes from the socket, or from `X-Forwarded-For` **only** when `TRUSTED_PROXY_COUNT` says a proxy is in front.

---

## 8. External APIs and integrations

### 8.1 Runtime

**None.** No analytics, CDN fonts, error-tracking services, LLM APIs or webhooks. This is a privacy rule, not a gap: any outbound call could carry document data.

### 8.2 Build time: model weights (D16)

| Item | Detail |
| --- | --- |
| Source | Private Hugging Face model repo `MODEL_REPO`, pinned to `MODEL_REVISION` (a commit hash, not a branch) |
| Auth | `HF_TOKEN` passed as a **Docker build secret**, read-only scope; never written into an image layer, never in the runtime environment |
| Integrity | After download, the SHA-256 of the weights must equal `MODEL_SHA256`, or the build fails |
| Fault tolerance | 3 retries with backoff (2 s, 8 s, 30 s); a failed download fails the build, never ships an image without a model |
| Result | Weights baked into the image at `NER_MODEL_PATH`; the running app never contacts Hugging Face |

### 8.3 Development only

| Integration | Use |
| --- | --- |
| GitHub + Actions | Code, CI, required checks, image build on tags |
| Hugging Face datasets (ai4privacy) | NER training in Colab; not part of the app |

---

## 9. Webhooks

**None in MVP.** Nothing outside the app needs to be told about events, and outbound calls are ruled out at runtime (8.1).

If a webhook is ever added (e.g. "scan finished" for an integration), it must follow these rules: payload holds ids, status and risk level only, never document data; signed with HMAC-SHA256 over `timestamp + "." + body` using a dedicated key, sent as a header with the timestamp; receivers reject messages older than 5 minutes; retries with backoff and an idempotency id per event; and its own ADR before it is built.

---

## 10. Environment variables

Server-side only. **The frontend receives none:** it is built without secrets and calls the API on the same origin.

### 10.1 Runtime

| Variable | Required | Default | Used by |
| --- | --- | --- | --- |
| `ENV` | no | `dev` | `prod` turns on `Secure` cookies, refuses DEV keys, hides `/docs` |
| `PUBLIC_ORIGIN` | **prod** | `http://localhost:8000` | `Origin` check (3.2) |
| `DATA_DIR` | no | `/data` | Database, checkpoints, files, anchor |
| `PG_TOKEN_KEY` | **prod** | DEV key in dev | HMAC tokens |
| `PG_AUDIT_KEY` | **prod** | DEV key in dev | Audit chain |
| `PG_VAULT_KEY` | **prod** | DEV key in dev | Vault |
| `PG_STORAGE_KEY` | **prod** | DEV key in dev | Files and checkpoints at rest |
| `NER_MODEL_PATH` | no | `/app/model` | Model folder in the image |
| `NER_THRESHOLD` | no | `0.5` | Fusion threshold |
| `MAX_UPLOAD_MB` | no | `10` | 4.5 |
| `RETENTION_DAYS` | no | `7` | Retention job |
| `SESSION_IDLE_HOURS` / `SESSION_MAX_DAYS` | no | `8` / `7` | 3.1 |
| `TRUSTED_PROXY_COUNT` | no | `0` | Client IP for rate limits |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | no | none | First admin, once, if no users exist; remove after first start |
| `LOG_LEVEL` | no | `INFO` | Logging |

### 10.2 Build time

| Variable | Kind | Used for |
| --- | --- | --- |
| `HF_TOKEN` | Build secret | Model download (8.2) |
| `MODEL_REPO` | Build arg | Model repo name |
| `MODEL_REVISION` | Build arg | Pinned commit |
| `MODEL_SHA256` | Build arg | Integrity check |

Startup refuses to run in `prod` if any key is missing, shorter than 32 bytes, reused for two purposes, or a DEV key (ADR-0020).

---

## 11. Data privacy

| Rule | How the API follows it |
| --- | --- |
| Personal data only to its owner | Only endpoints 7 (`context` snippets), 9 (`original_text`) and 10 (`cleaned` file) return document content, all owner-scoped |
| Real values only through reveal | Endpoint 15 is the only way to get a value behind a token; admin, reason, rate limit, audit-before-return |
| Nothing personal in URLs | Ids only in paths; tokens, reasons and text travel in bodies; download filenames use the scan id |
| Nothing cached | `Cache-Control: no-store` on every API response |
| Nothing personal in logs | Access logs record method, path template (`/scans/{id}`), status, duration, request id, user id; never bodies, query values, filenames or cookies. A test runs a full scan through the API and fails if any sample value appears in captured logs |
| Nothing personal in errors | Error messages are fixed strings from section 2.4 |
| Reports without values | The JSON report holds offsets, types, actions and tokens only |
| Deletion is real | `DELETE /scans/{id}` and the retention job remove rows, files, checkpoints and unused vault entries (DATABASE 10.3) |

---

## 12. Failure handling

| Failure | What the user sees | What the system does |
| --- | --- | --- |
| Model still loading after start | Scan stays `queued`; step 1 says "Preparing the model, about 30 seconds, only the first time" | Worker waits for `model_ready`, then runs the queue |
| Worker crash or app restart mid-scan | Scan continues after restart, or shows `failed` with Retry | Startup re-enqueues open scans; graph resumes from its last checkpoint |
| Parse failure (broken file, no text layer, timeout) | `failed` with the specific message | `error_code` and `step` saved; Retry allowed |
| Verifier cannot clean everything in 3 rounds | `done` with "N items could not be removed after 3 rounds" | `unresolved_leaks` > 0, shown in the risk banner and report |
| Database locked | Request fails with "Service busy" | One retry after 100 ms, then `503 busy` |
| Disk full | "Service unavailable" | `503 storage_unavailable`; upload rejected before any partial file is kept |
| Audit write fails | The action fails | Reveal: no value returned. Scan: scan fails rather than finishing unlogged |
| Vault entry tampered | "Vault entry failed integrity check" | `422 vault_integrity`; no value returned |
| Session expires mid-review | Sent to login, then back to the same scan | Answers not yet submitted are kept in the page; the paused scan is untouched |
| Network blip while polling | Nothing (silent retry) | Client retries GETs twice with backoff; never retries POSTs automatically |
| Double-click on a POST | One action happens | Buttons disable while in flight; answers and retry return `409` on a repeat, which the client treats as already done |
| Unexpected error | "Something went wrong. Quote request {id}." | `500 internal`, full details only in server logs under that request id |

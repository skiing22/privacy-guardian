# PRD: Privacy Guardian Agent v2

> **Source of truth for the coding agent.** Where this PRD and older docs (SRS, ADRs) disagree, this PRD wins, once the decisions in section 13 are approved.
>
> **Labels used:** `[ASSUMPTION]` = believed true, not confirmed. `[DECISION NEEDED]` = needs owner approval before build (none open: D1 to D12 approved 2026-11-19). `Status` = state of the code on `main` at tag `v0.5.0`.

---

## 1. Problem

People share documents that contain personal data (PII): resumes, hospital notes, bank letters, spreadsheets of customers. Before sharing, someone must find and hide every name, phone number, Aadhaar, PAN, address and so on.

- **Doing it by hand** is slow and people miss things.
- **Find-and-replace or regex tools** miss names and addresses, and flag harmless numbers (OTPs, order numbers).
- **Removing everything** makes the document useless for analysis.
- **Removing names is not enough.** Leftover clues (age + gender + PIN code) can still point to one person.
- **No proof.** Teams cannot show later who saw the real data, or that the log of actions was not edited.

## 2. Value proposition

Upload a document, get back a safe copy that is **still useful**, with an explanation of every choice and a **tamper-evident** record of what happened.

1. **Finds more, flags less noise:** checksums (Aadhaar, card) + a trained NER model + context words, combined so each covers the others' weak spots.
2. **Keeps data useful:** the same person gets the same pseudonym in every file; ages and dates are generalized instead of deleted.
3. **Measures leftover risk:** estimates how many people could still match the remaining clues, and protects more until risk is acceptable.
4. **Asks when unsure, and learns:** low-confidence items go to a human; answers update the system for next time.
5. **Proves integrity:** audit log is an HMAC hash chain; any edit is detected and located.

## 3. Target users

| User | Need | Example |
| --- | --- | --- |
| **Data handler** (primary) | Clean a document before sharing it | HR exec sharing resumes with a vendor; researcher sharing patient notes |
| **Reviewer** | Confirm or correct uncertain items quickly | Same person as data handler in MVP |
| **Admin / compliance** | Set rules, get a real value back when legally required, prove the log is intact | Data protection officer |

`[ASSUMPTION]` Users are in India; text is mostly English with Indian names, places and ID formats.
`[ASSUMPTION]` One organisation per deployment in MVP (see D3).

## 4. Core user journeys

**J1. Clean a document (happy path)**
Log in → upload file or paste text → watch progress → download cleaned file + report.

**J2. Review uncertain items**
Scan pauses → reviewer sees each uncertain item highlighted in context → chooses *protect*, *keep visible*, or *not PII* → scan continues → result.

**J3. Get a real value back (re-identification)**
Admin enters a token (e.g. `PERSON_c97ab2`) and a written reason → sees the original value → this action is recorded in the audit log.

**J4. Prove the log was not edited**
Admin opens audit log → clicks *Verify* → sees "OK, N records" or "Tampered at record #k: reason".

**J5. Set protection rules**
Admin sets a fixed action for a PII type (e.g. Aadhaar → always redact).

## 5. User stories

| ID | As a… | I want to… | So that… | Priority |
| --- | --- | --- | --- | --- |
| US-1 | Data handler | upload TXT, PDF, DOCX or CSV (≤10 MB) | I can clean my real files | Must |
| US-2 | Data handler | see which items were found and what was done to each, and why | I can trust the output | Must |
| US-3 | Data handler | download a cleaned file and a JSON report | I can share it | Must |
| US-4 | Data handler | see a risk level for the cleaned file | I know if it is safe to share | Must |
| US-5 | Reviewer | answer protect / keep / not PII for uncertain items | the result is right and the system learns | Must |
| US-6 | Data handler | see progress while a scan runs | I know it is working | Should |
| US-7 | Data handler | come back later to a paused scan | review does not have to happen at once | Should |
| US-8 | Admin | set a fixed action per PII type | company rules are always followed | Must |
| US-9 | Admin | get the real value behind a token with a reason | I can meet legal requests | Must |
| US-10 | Admin | verify the audit log | I can prove nothing was edited | Must |
| US-11 | Data handler | see my past scans | I can re-download results | Should |

## 6. Features and functional requirements

`Status`: ✅ built and tested · 🟡 partly built · ⬜ not built.

### 6.1 Input
| ID | Requirement | Status |
| --- | --- | --- |
| FR-01 | Accept pasted text and TXT, PDF (text layer only), DOCX, CSV up to 10 MB | ✅ |
| FR-02 | Keep a map from every character back to its place in the file (page, paragraph, row/column) | ✅ |
| FR-03 | Split long text into overlapping chunks so the model never silently cuts text | ✅ |
| FR-04 | For CSV, detect which whole columns hold PII | ✅ |

### 6.2 Detection
| ID | Requirement | Status |
| --- | --- | --- |
| FR-05 | Rules for email, phone, Aadhaar, PAN, IFSC, card, IP | ✅ |
| FR-06 | Checksums (Verhoeff for Aadhaar, Luhn for cards) to drop false matches | ✅ |
| FR-07 | Trained NER model for names, places, addresses, dates, IDs (runs on CPU) | ✅ |
| FR-08 | Context words lower/raise scores (e.g. "OTP 482913" is not PII) | ✅ |
| FR-10 | Run detectors in parallel and combine | ✅ |

### 6.3 Combining and reasoning
| ID | Requirement | Status |
| --- | --- | --- |
| FR-11 | Merge overlapping finds; a passed checksum beats a model guess | ✅ |
| FR-12 | One confidence per item; agreeing detectors raise it | ✅ |
| FR-13 | Link mentions of one entity ("Rahul Sharma", "Rahul", "Mr. Sharma"); never link when ambiguous | ✅ |
| FR-14 | Re-identification risk from leftover clues (LOW / MEDIUM / HIGH / DIRECT) | ✅ |

### 6.4 Learning
| ID | Requirement | Status |
| --- | --- | --- |
| FR-15–17 | Per PII type, learn *how sensitive* it is and *how often flags are right*, from review answers; keep this between runs | ✅ (in memory + JSON file; database in M5) |

### 6.5 Actions and policy
| ID | Requirement | Status |
| --- | --- | --- |
| FR-18 | Choose per item: keep, generalize, mask, pseudonymize, redact, by a utility score | ✅ |
| FR-19 | Generalize age → 5-year band, date → year, PIN → first 3 digits | ✅ |
| FR-20 | Admin fixed action per type overrides the score | ✅ (logic) · ⬜ (screen) |
| FR-20a | If risk is still too high, strengthen the most identifying item until it is acceptable | ✅ |
| FR-20b | Keep toll-free business numbers (1800/1860) | ✅ |

### 6.6 Agent workflow
| ID | Requirement | Status |
| --- | --- | --- |
| FR-21 | Stricter second check on the output; loop back if anything leaked (max 3 rounds); report anything left | ✅ |
| FR-22 | Pause for human review on low confidence, ambiguous names, or unreliable types | ✅ |
| FR-23 | A paused or crashed scan resumes from where it stopped | 🟡 (works in memory; needs database checkpoints) |

### 6.7 Crypto
| ID | Requirement | Status |
| --- | --- | --- |
| FR-24 | Pseudonym = keyed HMAC of the normalized value; same value → same token in every file; collision check | ✅ |
| FR-25 | Encrypted vault (AES-GCM) maps token → value | ✅ |
| FR-26–27 | Audit log as HMAC hash chain; verify names the first bad record; external anchor | ✅ |
| FR-29 | Key IDs so keys can be rotated | ✅ |
| FR-33 | Re-identify only for admin, needs a reason, always logged | ✅ (logic) · ⬜ (screen) |

### 6.8 Delivery
| ID | Requirement | Status |
| --- | --- | --- |
| FR-30 | Download cleaned output + JSON report | ⬜ — format: see **D4** |
| FR-31 | Live progress per step | ⬜ — method: see **D6** |
| FR-32 | Login with roles | ⬜ |
| FR-34 | Scan history per user | ⬜ |

## 7. Non-functional requirements

| ID | Area | Target | Status |
| --- | --- | --- | --- |
| NFR-01 | Accuracy | Span F1 ≥ 0.90 on a **held-out** hand-written Indian test set never used to tune rules | ❌ **0.795 on held-out set v2** (`docs/results/handwritten-v2.md`); 0.922 on v2 after the address fix (ADR-0024), but v2 guided that fix, so it needs set v3. Checksum-type precision 1.0. |
| NFR-02 | Speed | 1 page (~500 words) in < 5 s on CPU, model already loaded | ✅ ~0.3–0.5 s measured; model load ~30 s once at startup |
| NFR-03 | Responsiveness | UI never freezes during a scan | ⬜ |
| NFR-04 | Privacy | Raw PII never in logs or audit payloads; uploaded files deleted after 7 days `[ASSUMPTION]` | ✅ (logs) · ⬜ (deletion) |
| NFR-05 | Security | Keys only from environment; 3 separate keys; bcrypt passwords; HTTPS in production; rate limit on login | 🟡 keys ✅ |
| NFR-06 | Integrity | Any edit to the audit log is detected | ✅ |
| NFR-07 | Reliability | Resume after restart | 🟡 |
| NFR-08 | Quality | CI must pass before merge; coverage ≥ 70% | ✅ 125 tests, 96% |
| NFR-09 | Portability | Whole app starts with one command (`docker compose up`) | 🟡 backend only |

## 8. Pages / screens

MVP has **6 app screens** plus 3 static pages approved later (D11, D12). Insights / charts screen is cut from MVP (was in SRS 6.1).

| # | Screen | Who | What it shows |
| --- | --- | --- | --- |
| S1 | Login | All | Email + password |
| S2 | Scans (home) | All | List of my scans: name, date, status, risk level; "New scan" button |
| S3 | New scan | All | File upload or paste box; Start |
| S4 | Scan detail | All | **While running:** progress steps. **Paused:** review panel. **Done:** original vs cleaned side by side, colour-coded items, table of item / type / action / reason, risk level, download buttons |
| S5 | Admin: rules & vault | Admin | Fixed action per PII type; re-identify form (token + reason) |
| S6 | Admin: audit log | Admin | Table of events; Verify button with result |
| S0 | Public landing page (D12) | Anyone | What the tool does, real screenshot of S4, one action: "Try the demo". Built last (M7) |
| S7 | Privacy and terms (D11) | Anyone | Plain statement of what is stored, for how long, and who can see it; linked from every footer |
| S8 | Not found (D11) | Anyone | "This page does not exist." + link back |

**D7 (approved):** S4 combines run, review and result into one page.

## 9. Roles and permissions

| Action | User | Admin |
| --- | --- | --- |
| Scan, review own scans, download own results | ✅ | ✅ |
| See other users' scans | ❌ | ❌ `[ASSUMPTION]` admins see audit events, not other users' documents |
| Change fixed rules per PII type | ❌ | ✅ |
| Re-identify a token (reason required) | ❌ (attempt is logged) | ✅ (logged) |
| View and verify audit log | ❌ | ✅ |
| Create users | ❌ | ✅ (MVP: via a command-line script, no screen) |

## 10. Data requirements

| Data | Holds | Kept for | Notes |
| --- | --- | --- | --- |
| users | email, password hash, role | until deleted | bcrypt |
| scans | owner, file name, status, risk level, rounds, timings | 90 days `[ASSUMPTION]` | no raw text |
| documents | uploaded file (encrypted at rest) + cleaned output | **7 days** `[ASSUMPTION]` | deleted by a daily job |
| decisions | per item: offsets, type, action, reason, token | with scan | no raw values; values only in vault |
| beliefs | per PII type: two Beta distributions | permanent | admin can reset |
| policy | per PII type: fixed action (optional) | permanent | |
| vault | token, type, key id, nonce, ciphertext | **7 days**, deleted with the document (D8) | only place real values live |
| token registry | token, full HMAC, key id | permanent | for collision check |
| audit log | seq, time, actor, event, payload, prev mac, mac, key id | permanent, append-only | never raw PII |
| graph checkpoints | paused/in-progress scan state | until scan done + 1 day | contains raw text while running |

**Keys:** 3 secrets (token, audit, vault) from environment variables. Never in the database or repo.

## 11. Integrations

| Integration | Use | MVP? |
| --- | --- | --- |
| Hugging Face model files | NER weights, downloaded at build time, ~260 MB | Yes |
| PostgreSQL | app data + LangGraph checkpoints | Yes, see **D2** |
| GitHub Actions | CI | Yes (done) |
| Hosting provider | run the app | Yes, see **D1** |
| External LLM API | hard cases | **No** (out of scope) |
| Email / SSO | password reset, company login | **No** |

## 12. Loading, empty and error states

| Screen | Loading | Empty | Errors (message shown) |
| --- | --- | --- | --- |
| S1 Login | Button spinner | — | "Wrong email or password" (same text for both, no hint which); "Too many tries, wait 1 minute" |
| S2 Scans | Skeleton rows | "No scans yet. Start your first scan." + button | "Could not load scans. Retry." |
| S3 New scan | Upload progress bar | Start disabled until file/text given | "File too large (max 10 MB)"; "Only TXT, PDF, DOCX, CSV"; "This PDF has no text (scanned image). Not supported yet." |
| S4 Scan – running | Step list: Reading file → Detecting → Combining → Choosing actions → Checking for leaks (round n) → Done | — | "Scan failed at step X. Retry." (scan stays resumable) |
| S4 Scan – paused | — | — | "Your answers could not be saved. Retry." |
| S4 Scan – done | — | "No personal data found." + still offer download | Risk shown as banner: **HIGH** red ("Do not share"), **DIRECT** red ("Personal data still visible because of a rule"), **MEDIUM** amber, **LOW** green; "N items could not be removed after 3 rounds" if any |
| S5 Rules & vault | Spinner | "No fixed rules. All types use automatic choice." | Re-identify: "Only admins can do this"; "Reason must be at least 10 characters"; "Unknown token"; "Vault entry failed integrity check" |
| S6 Audit log | Skeleton rows | "No events yet." | Verify: green "OK: N records verified (matches anchor)" or red "Tampered at record #k: reason" |
| Any | — | — | Session expired → back to login with "Please log in again"; server down → "Service unavailable. Try again shortly." |

## 13. Decisions (all approved by the owner on 2026-11-19)

Recommendations favour **finishing a working, deployed MVP** over adding scope.

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| **D1** | Hosting | (a) Hugging Face Spaces (Docker, enough RAM for model, sleeps when idle) (b) Render (may lack RAM) (c) own VM | **(a)** backend; frontend on same container or Vercel |
| **D2** | Database | (a) PostgreSQL (b) SQLite file | **(b) SQLite for MVP.** One user at a time, free hosting, no separate DB service; LangGraph has a SQLite checkpointer. Code already uses small store interfaces, so Postgres later is a swap. *Reverses SRS/ADR-0006.* |
| **D3** | Organisations | (a) many orgs with separate beliefs (b) one org per deployment | **(b)**. Learning code already keys by org; just fix it to one. |
| **D4** | Output format | (a) same format as input for all 4 (b) TXT/CSV/DOCX same format, PDF → cleaned .txt (c) .txt for all | **(b)**. Rewriting PDFs in place is hard and error-prone. |
| **D5** | Frontend | (a) React SPA (b) server-rendered pages (FastAPI + templates + a little JS) | **(a) React**, but only the 6 screens in section 8 |
| **D6** | Live progress | (a) Server-Sent Events (b) poll every 1 s | **(b) polling** for MVP; scans finish in ~1 s after model load. SSE later if needed. |
| **D7** | One combined scan page | yes / no | **yes** |
| **D8** | Vault retention | (a) forever (b) delete with document after 7 days | **(b)**. Once a document is gone, keeping a way to re-identify it adds risk with little use. Tokens still stay consistent (HMAC needs no vault). |
| **D9** | Accuracy claim | (a) quote 0.976 (b) build held-out set v2 (~30 texts written by someone who has not seen fusion rules), quote that | **(b)** before any resume/README number |
| **D10** | Anchor storage | (a) local file (b) daily commit of latest mac to a separate GitHub repo (c) none | **(a) for MVP demo**, document (b) as production step |
| **D11** | Privacy and terms page + 404 page | add / skip | **Add** (static pages, linked from footer) |
| **D12** | Public landing page S0 for recruiters | add / skip | **Add, built last in M7**; no invented numbers; accuracy figure waits for D9 |

**Already-built items that could be seen as over-engineering** (keep or drop — owner decides; recommendation is keep, no further work):
- Belief decay (forgetting old feedback) — off by default.
- Key rotation with key IDs — kept, no screen.
- CSV whole-column detection — kept, shown only in report.

## 14. MVP scope

**In:**
- Everything marked ✅ in section 6 (already built).
- FR-23 with database checkpoints, FR-30 (per D4), FR-31 (per D6), FR-32, FR-34.
- Screens S1–S6, static pages S7 and S8, and the landing page S0 (last, in M7).
- Admin user created by script.
- File deletion job (NFR-04).
- Docker image + one public demo deployment (D1).
- README with architecture diagram, results and how to run.
- Held-out test set v2 and its score (D9).

**Out of scope (MVP):**
- Scanned PDFs / images (OCR), audio, non-English text.
- External LLM detector (FR-09).
- HMAC-signed reports (FR-28); public-key signatures.
- Multiple organisations, SSO, email, password reset.
- Insights/charts screen, beliefs-over-time charts.
- Marketing site beyond the single S0 page.
- Developer API keys and public API docs beyond FastAPI's auto `/docs`.
- UPI IDs and landline numbers as PII types (known gaps).
- ORG detection (no training data; known gap).
- Batch / bulk upload.

## 15. Success criteria

MVP is done when **all** are true:

1. A new user can go from login → upload → review → download on the **public demo URL** in under 2 minutes, with no help.
2. Held-out test set v2: span F1 **≥ 0.90**, and precision on checksum types (Aadhaar, card) = **1.0**.
3. Sample patient note: zero direct identifiers in output; risk LOW or MEDIUM; same person → one token.
4. Restarting the server during a paused review, then answering, completes the scan.
5. Editing any audit log row by hand makes Verify report that exact row.
6. Re-identify by a non-admin, or without a reason, is refused **and** logged.
7. No raw PII appears in application logs or audit payloads (checked by test).
8. CI green on `main`; coverage ≥ 70%; every design choice has an ADR.
9. One-page page load < 2 s; scan of a 1-page document < 5 s after model load.

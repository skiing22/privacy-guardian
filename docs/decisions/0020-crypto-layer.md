# ADR-0020: Crypto layer as built - HMAC tokens, AES-GCM vault, audit chain with anchor

- Status: Accepted
- Date: 2026-11-18
- Implements: ADR-0002, ADR-0003
- Requirements: FR-24 to FR-27, FR-29, FR-33, NFR-04, NFR-06

## Decision (`backend/app/crypto/`)
**Keys (`keys.py`).** Three purposes (token, audit, vault), three independent 256-bit keys from env vars. Each key has an id; the newest is last and used for new data, older ones stay for checking/decrypting old data (FR-29). Startup refuses short keys, missing keys, or the same key used for two purposes. `repr` never prints key bytes. `KeyRing.dev()` gives fixed keys for demos and tests only.

**Tokens (`tokens.py`).** `TYPE_` + first 6 hex of HMAC-SHA256(K1, TYPE || 0x00 || normalize(value)).
- Normalization (ADR-0014) means "98470 12345" and "+91 9847012345" share a token, across documents.
- The type is inside the MAC: "Kochi" as PERSON and as LOCATION are unrelated (domain separation).
- Entity linking picks one canonical value per entity, so "Rahul" and "Rahul Sharma" in one document share the token of "Rahul Sharma".
- Collision check: the registry stores the full MAC per issued token; if a prefix is taken by a different value, the new value gets a longer token. A test forces 1-hex tokens over 200 values and checks no token ever covers two values.

**Vault (`vault.py`).** AES-256-GCM, random 96-bit nonce per entry, associated data = token | type | key id, so a ciphertext moved onto another token's row fails authentication. `put` is idempotent (graph nodes may re-run on resume). Re-identify needs role admin and a reason of 10+ characters; denied attempts are logged; success is logged before the value is returned.

**Audit (`audit.py`).** mac_i = HMAC(K2, canonical(seq, ts, actor, event, payload_hash, prev_mac, kid)). Canonical JSON (sorted keys, no spaces). Verify reports the first bad record and why: payload changed, mac mismatch, record removed/inserted, sequence gap. Each record carries its key id, so the chain verifies across rotation.
- **Anchor:** (seq, mac) of the latest record, to be copied off the server. A test shows the honest limit: an attacker holding K2 can rebuild a chain that verifies on its own, but it no longer matches the anchor. Anchors also catch truncation of the tail.
- **No raw PII in the log (NFR-04):** payloads hold scan ids, types, verdicts, counts and tokens only. Tests assert names never appear in the log.

**Graph integration.** `GraphDeps.crypto` (optional). With it: HMAC tokens instead of PERSON_1, vault entries for every pseudonymized entity, audit events `review` (after the human answers, so a resumed node logs once) and `scan_completed`. Without it: readable ids, as before (tests and quick demos).

**CLI demo.** `scan` (crypto on by default), `reidentify TOKEN --reason ...`, `audit verify|anchor|show`. Stores are plain files in `data/` (git-ignored); `audit.jsonl` is readable on purpose, so a hand edit can be shown to fail verification.

## Consequences
- Rotating K1 changes future tokens for the same value (old documents keep old tokens). Linking old to new needs the vault or a re-tokenize job. Accepted: rotation should be rare.
- The anchor is only as good as where it is stored; M5/M7 should write it somewhere the app server cannot rewrite (e.g. a scheduled git commit or a separate service).
- HMAC signatures on reports (FR-28) stay "Could"; Ed25519 would let outsiders verify.

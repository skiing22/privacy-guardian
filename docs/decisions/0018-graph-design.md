# ADR-0018: Graph design - parallel detectors, review interrupt, stricter verifier loop

- Status: Accepted
- Date: 2026-11-18
- Builds on: ADR-0001
- Requirements: FR-10, FR-21, FR-22, FR-23

## Context
v1 was criticised as "agents called one after another, one episode at a time". ADR-0001 chose LangGraph; this ADR fixes the concrete shape (`backend/app/graph/`).

## Decision
**Shape:** `START -> detect_rules | detect_ner | detect_context (parallel) -> fuse -> review -> policy -> verify -> (next_round -> detectors) | finalize`.

1. **Fan-out / fan-in (FR-10).** One node per detector, all started from START. Each writes its own key in `candidates` (dict-merge reducer), so parallel writes never clash; `fuse` runs only after all have finished.
2. **Human review (FR-22).** In round 0, spans go to review if: confidence < 0.7, the name is ambiguous (ADR-0014), or the type's learned precision < 0.6 (ADR-0016). The node calls `interrupt()`; the graph pauses and the API gets the items. The reviewer's answers resume it (`Command(resume=...)`) and are recorded as belief feedback (FR-16): `not_pii` drops the span, `keep` and `protect` force an action that the risk loop cannot change.
3. **Verifier loop (FR-21).** `verify` re-runs all detectors on the cleaned output with a lower threshold (0.35 vs 0.5): a stricter second opinion with more recall. It ignores our own placeholders (PERSON_1, [REDACTED], masks) and values we chose to leave visible. If something leaked, `next_round` scans the output again and protects every new find (gain >= 0.9). At most 3 rounds; leftovers are reported as `unresolved_leaks`, not hidden.
4. **A human verdict beats the verifier.** Values a reviewer marked `not_pii` go on the allowed list, or the stricter verifier would overrule the human in round 2 (found by a test).
5. **Checkpointing (FR-23).** Every node's output is checkpointed per `thread_id` (= scan id). A paused or crashed scan resumes from the last node, even in a new process. In-memory saver for tests; Postgres saver in M5.
6. **Safe deserialization.** The checkpoint serializer only rebuilds an allow-list of our own types, so a tampered checkpoint cannot build arbitrary objects.
7. **Observability.** Every node appends an `Event(node, round, ms, info)`; M5 streams these to the UI (FR-31).

## Consequences
- On the 32 hand-written examples (cached NER): all end at risk LOW, 0 unresolved leaks; 1 needed a second round.
- The verifier reuses the same detectors, so it mainly catches low-confidence misses; a different model (e.g. the optional LLM detector, FR-09) would make it a truly independent check.
- Review answers refer to span indexes of that scan; the API must send them back unchanged.

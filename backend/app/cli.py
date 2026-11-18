"""Command-line demo: scan a file with the full agent graph on your own machine.

    cd backend
    python -m app.cli scan ../data/samples/patient_note.txt
    python -m app.cli scan resume.pdf --auto        # no review questions
    python -m app.cli scan people.csv --columns     # also classify CSV columns (FR-04)

Beliefs are saved to a JSON file between runs (FR-17): answer "keep" for a type a few
times and watch the next scan treat it differently.
"""

import argparse
import json
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.crypto.audit import Anchor
from app.crypto.filestore import JsonlAuditStore, JsonTokenRegistry, JsonVaultStore
from app.crypto.keys import KeyConfigError, KeyRing
from app.crypto.services import CryptoServices
from app.crypto.vault import VaultError
from app.detectors.context import ContextDetector
from app.detectors.rules import RuleDetector
from app.detectors.types import Span
from app.fusion.fuse import fuse
from app.graph.build import (
    Detector,
    GraphDeps,
    build_graph,
    pending_review,
    result_of,
    resume_scan,
    start_scan,
)
from app.graph.state import ScanResult
from app.parsers.chunking import ChunkedDetector
from app.parsers.files import classify_columns, parse_file
from app.policy.beliefs import BeliefLearner, Feedback, InMemoryBeliefStore

Ask = Callable[[dict[str, Any]], dict[str, Any]]
_CHOICES = {"p": Feedback.PROTECT, "k": Feedback.KEEP, "n": Feedback.NOT_PII}


def ask_terminal(item: dict[str, Any]) -> dict[str, Any]:
    print(f"\n  ? {item['pii_type']:<9} {item['text']!r}  ({item['reason']}, {item['score']:.2f})")
    while True:
        a = input("    [p]rotect / [k]eep visible / [n]ot PII > ").strip().lower()[:1]
        if a in _CHOICES:
            return {"index": item["index"], "verdict": _CHOICES[a].value}


def default_detectors(model: str) -> dict[str, Detector]:
    from app.detectors.ner import NerDetector

    return {
        "rules": RuleDetector(),
        "ner": ChunkedDetector(NerDetector(model, threshold=0.3)),
        "context": ContextDetector(),
    }


def fused_detector(detectors: dict[str, Detector]) -> Callable[[str], list[Span]]:
    """Rules + NER + context, then fusion: the same evidence the graph uses (not NER alone)."""

    def detect(text: str) -> list[Span]:
        raw = [s for d in detectors.values() for s in d.detect(text)]
        return fuse(text, raw)

    return detect


def load_keys() -> KeyRing:
    try:
        return KeyRing.from_env()
    except KeyConfigError:
        print("! PG_*_KEY not set: using fixed DEV keys (fine for a demo, never in production)")
        return KeyRing.dev()


def crypto_services(data_dir: Path, actor: str = "cli") -> CryptoServices:
    return CryptoServices.build(
        load_keys(),
        audit_store=JsonlAuditStore(data_dir / "audit.jsonl"),
        vault_store=JsonVaultStore(data_dir / "vault.json"),
        registry=JsonTokenRegistry(data_dir / "tokens.json"),
        actor=actor,
    )


def scan(
    text: str,
    detectors: dict[str, Detector],
    learner: BeliefLearner,
    org: str,
    ask: Ask | None,
    crypto: CryptoServices | None = None,
) -> ScanResult:
    deps = GraphDeps(detectors=detectors, learner=learner, crypto=crypto)
    if ask is None:
        deps.review_threshold, deps.min_precision = 0.0, 0.0
    app = build_graph(deps)
    tid = str(uuid.uuid4())
    state = start_scan(app, text, tid, org)
    items = pending_review(state)
    if items:
        assert ask is not None
        print(f"\n{len(items)} item(s) need your review:")
        state = resume_scan(app, tid, [ask(it) for it in items])
    return result_of(state)


def print_result(res: ScanResult, locate: Callable[[int], str | None]) -> None:
    print("\n=== cleaned output ===\n" + res.output)
    r = res.risk
    print(f"\n=== risk: {r.level.value}  (~{r.est_matches:,.0f} people match; clues: "
          f"{', '.join(r.clues) or 'none'}) ===")  # fmt: skip
    first = res.history[0]
    print("\n=== decisions (round 1) ===")
    for s, d in zip(first.spans, first.decisions, strict=True):
        where = locate(s.start) or ""
        print(f"  {s.pii_type.value:<10} {s.text[:28]!r:<31} {d.action.value:<13} "
              f"{d.reason:<16} {where}")  # fmt: skip
    print(f"\n=== {res.rounds} round(s); timings ===")
    for e in res.events:
        print(f"  r{e.round + 1} {e.node:<16} {e.ms:>8.1f} ms  {e.info}")
    if res.unresolved_leaks:
        print(f"\n!! {len(res.unresolved_leaks)} unresolved leak(s) after max rounds")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="scan a TXT, PDF, DOCX or CSV file")
    sc.add_argument("file")
    sc.add_argument("--model", default="../ml/models/ner-distilbert-v1")
    sc.add_argument("--org", default="demo")
    sc.add_argument("--beliefs", default="../data/beliefs.json")
    sc.add_argument("--auto", action="store_true", help="no review questions")
    sc.add_argument("--columns", action="store_true", help="CSV: classify whole columns")
    sc.add_argument("--no-crypto", action="store_true", help="readable ids, no vault/audit")
    sc.add_argument("--data", default="../data")

    rd = sub.add_parser("reidentify", help="token -> original value (admin, logged)")
    rd.add_argument("token")
    rd.add_argument("--reason", required=True)
    rd.add_argument("--actor", default="admin-cli")
    rd.add_argument("--role", default="admin")
    rd.add_argument("--data", default="../data")

    au = sub.add_parser("audit", help="verify or anchor the audit log")
    au.add_argument("action", choices=["verify", "anchor", "show"])
    au.add_argument("--data", default="../data")
    au.add_argument("--anchor-file", default="../data/audit.anchor.json")
    args = ap.parse_args(argv)

    if args.cmd == "reidentify":
        return cmd_reidentify(args)
    if args.cmd == "audit":
        return cmd_audit(args)

    doc = parse_file(args.file)
    print(f"parsed {args.file}: {doc.fmt}, {len(doc.text):,} chars, {len(doc.segments)} segments")

    bpath = Path(args.beliefs)
    store = (
        InMemoryBeliefStore.from_json(bpath.read_text())
        if bpath.exists()
        else InMemoryBeliefStore()
    )
    learner = BeliefLearner(store)
    detectors = default_detectors(args.model)
    t0 = time.perf_counter()
    detectors["ner"].detect("warm up")  # load weights now, not inside the timed graph
    print(f"model loaded in {time.perf_counter() - t0:.1f} s")

    if args.columns and doc.fmt == "csv":
        print("\n=== CSV columns ===")
        for v in classify_columns(Path(args.file).read_bytes(), fused_detector(detectors)):
            print(f"  {v.column:<16} {v.pii_type.value if v.pii_type else '-':<10} "
                  f"{v.share:.0%} of {v.sampled}")  # fmt: skip

    crypto = None if args.no_crypto else crypto_services(Path(args.data))
    ask = None if args.auto else ask_terminal
    res = scan(doc.text, detectors, learner, args.org, ask, crypto)
    print_result(res, doc.locate)

    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(store.to_json())
    print(f"\nbeliefs saved to {bpath}")
    return 0


def cmd_reidentify(args: argparse.Namespace) -> int:
    c = crypto_services(Path(args.data), actor=args.actor)
    try:
        value = c.vault.reidentify(args.token, args.actor, args.role, args.reason)
    except VaultError as e:
        print(f"refused: {e}")
        return 1
    print(f"{args.token} -> {value}   (logged as audit #{c.audit.store.all()[-1].seq})")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    c = crypto_services(Path(args.data))
    apath = Path(args.anchor_file)
    if args.action == "show":
        for r in c.audit.store.all():
            print(f"#{r.seq:<3} {r.ts}  {r.actor:<10} {r.event:<17} {json.dumps(r.payload)[:70]}")
        return 0
    if args.action == "anchor":
        a = c.audit.anchor()
        if a is None:
            print("audit log is empty")
            return 1
        apath.write_text(json.dumps({"seq": a.seq, "mac": a.mac}))
        print(f"anchored seq {a.seq}: {a.mac[:16]}...  (in production: copy this OFF the server)")
        return 0
    anchor = Anchor(**json.loads(apath.read_text())) if apath.exists() else None
    res = c.audit.verify(anchor)
    if res.ok:
        extra = f", matches anchor at seq {anchor.seq}" if anchor else ", no anchor"
        print(f"OK: {res.checked} records verified{extra}")
        return 0
    print(f"TAMPERED at record #{res.first_bad_seq}: {res.reason}")
    return 2


if __name__ == "__main__":
    sys.exit(main())

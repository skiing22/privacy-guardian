"""The Privacy Guardian agent graph (ADR-0001, ADR-0018).

    START -> [detect_rules | detect_ner | detect_context]   (parallel fan-out)
          -> fuse                                           (fan-in: waits for all)
          -> review?  -- low confidence / ambiguous --> interrupt() for a human
          -> policy   (utility + risk loop)
          -> verify   (stricter second pass on the output)
          -> leak and rounds left? -> next_round -> detectors again
          -> finalize -> END

State is checkpointed after every node, so a scan paused for review (or a crashed one)
resumes from where it stopped.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt

from app.crypto.services import CryptoServices
from app.detectors.types import PiiType, Span
from app.fusion.fuse import fuse
from app.fusion.linking import link
from app.fusion.normalize import normalize
from app.fusion.risk import assess
from app.graph.serde import make_serde
from app.graph.state import Event, GraphState, ReviewItem, RoundRecord, ScanResult
from app.policy.actions import PRIVACY_GAIN, Action, allowed, generalize
from app.policy.beliefs import BeliefLearner, Feedback, InMemoryBeliefStore
from app.policy.utility import PolicyConfig, decide, visible_spans

# What our own actions write into the text; the verifier must not flag these.
_PLACEHOLDER = re.compile(r"\b[A-Z][A-Z_]*_(?:\d+|[0-9a-f]{6,64})\b|\[REDACTED\]|[X*]{2,}")


class Detector(Protocol):
    def detect(self, text: str) -> list[Span]: ...


@dataclass
class GraphDeps:
    detectors: dict[str, Detector]
    learner: BeliefLearner = field(default_factory=lambda: BeliefLearner(InMemoryBeliefStore()))
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    fuse_threshold: float = 0.5
    verify_threshold: float = 0.35  # stricter second pass: more recall
    review_threshold: float = 0.7
    min_precision: float = 0.6  # types flagged wrongly too often go to review
    max_rounds: int = 3
    crypto: CryptoServices | None = None  # None: readable ids (PERSON_1), no vault/audit


def _timed(name: str, fn: Callable[[GraphState], dict[str, Any]]) -> Callable[..., Any]:
    def node(state: GraphState) -> dict[str, Any]:
        t0 = time.perf_counter()
        out = fn(state)
        ms = round((time.perf_counter() - t0) * 1000, 2)
        info = out.pop("_info", "")
        out["events"] = [Event(name, state.get("round", 0), ms, str(info))]
        return out

    return node


def filter_known(text: str, spans: list[Span], allowed_values: list[str]) -> list[Span]:
    """Drop spans that are our own placeholders or values we chose to leave visible."""
    marks = [(m.start(), m.end()) for m in _PLACEHOLDER.finditer(text)]
    for v in {v for v in allowed_values if v.strip()}:
        # pieces of a value we chose to show ("30" inside "30-34") are not leaks
        marks += [(m.start(), m.end()) for m in re.finditer(re.escape(v), text)]
    ok = {v.lower() for v in allowed_values}
    out = []
    for s in spans:
        if any(a <= s.start and s.end <= b for a, b in marks):
            continue
        if any(a < s.end and s.start < b for a, b in marks) and _PLACEHOLDER.search(s.text):
            continue
        if s.text.lower() in ok or normalize(s.text, s.pii_type).lower() in ok:
            continue
        out.append(s)
    return out


def build_graph(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[Any, Any, Any, Any]:
    g: StateGraph[Any, Any, Any, Any] = StateGraph(GraphState)
    names = [f"detect_{n}" for n in deps.detectors]

    def make_detector(name: str, det: Detector) -> Callable[[GraphState], dict[str, Any]]:
        def run(state: GraphState) -> dict[str, Any]:
            found = det.detect(state["text"])
            return {"candidates": {name: found}, "_info": f"{len(found)} found"}

        return run

    for n, det in deps.detectors.items():
        g.add_node(f"detect_{n}", _timed(f"detect_{n}", make_detector(n, det)))

    def fuse_node(state: GraphState) -> dict[str, Any]:
        text = state["text"]
        raw = [s for spans in state["candidates"].values() for s in spans]
        thr = deps.fuse_threshold if state.get("round", 0) == 0 else deps.verify_threshold
        spans = fuse(text, raw, thr)
        if state.get("round", 0) > 0:
            spans = filter_known(text, spans, state.get("allowed_values", []))
        return {"spans": spans, "_info": f"{len(raw)} -> {len(spans)} spans"}

    def review_gate(state: GraphState) -> dict[str, Any]:
        """FR-22. Only in round 0; later rounds handle leaks automatically."""
        if state.get("round", 0) > 0:
            return {"review_items": [], "forced": {}}
        spans, org = state["spans"], state.get("org", "default")
        ambiguous = {i for e in link(spans) if e.ambiguous for i in e.mentions}
        items: list[ReviewItem] = []
        for i, s in enumerate(spans):
            prec = deps.learner.store.get(org, s.pii_type).precision.mean
            reason = (
                "ambiguous name" if i in ambiguous
                else "low confidence" if s.score < deps.review_threshold
                else "unreliable type" if prec < deps.min_precision
                else None
            )  # fmt: skip
            if reason:
                items.append(ReviewItem(i, s.text, s.pii_type.value, s.score, reason))
        if not items:
            return {"review_items": [], "forced": {}, "_info": "no review needed"}

        answers = interrupt({"items": [vars(it) for it in items]})  # graph pauses here

        forced: dict[int, Action] = {}
        drop: set[int] = set()
        new_spans = list(spans)
        for ans in answers:
            i, verdict = int(ans["index"]), Feedback(ans["verdict"])
            s = spans[i]
            if ans.get("pii_type"):
                s = Span(s.start, s.end, s.text, PiiType(ans["pii_type"]), s.score, s.source)
                new_spans[i] = s
            deps.learner.record(org, s.pii_type, verdict)  # FR-16: learning
            if verdict is Feedback.NOT_PII:
                drop.add(i)
            elif verdict is Feedback.KEEP:
                forced[i] = Action.KEEP
            elif verdict is Feedback.PROTECT:
                forced[i] = (
                    Action.PSEUDONYMIZE
                    if Action.PSEUDONYMIZE in allowed(s.pii_type, s.text)
                    else Action.REDACT
                )
        if deps.crypto:
            verdicts = [
                {"type": new_spans[int(a["index"])].pii_type.value, "verdict": a["verdict"]}
                for a in answers
            ]  # types and verdicts only: never the raw values (NFR-04)
            deps.crypto.audit.append(
                deps.crypto.actor, "review", {"scan": state.get("scan_id", ""), "answers": verdicts}
            )
        keep_idx = [i for i in range(len(new_spans)) if i not in drop]
        remap = {old: new for new, old in enumerate(keep_idx)}
        # a human cleared these: the verifier must never overrule that
        cleared = [spans[i].text for i in drop]
        return {
            "spans": [new_spans[i] for i in keep_idx],
            "allowed_values": [*state.get("allowed_values", []), *cleared],
            "review_items": items,
            "forced": {remap[i]: a for i, a in forced.items() if i in remap},
            "_info": f"{len(items)} reviewed",
        }

    def policy_node(state: GraphState) -> dict[str, Any]:
        text, spans, org = state["text"], state["spans"], state.get("org", "default")
        forced = dict(state.get("forced", {}))
        if state.get("round", 0) > 0:  # anything found now was missed before: protect it
            for i, s in enumerate(spans):
                strong = [a for a in allowed(s.pii_type, s.text) if PRIVACY_GAIN[a] >= 0.9]
                forced.setdefault(i, strong[0])
        tokenizer = deps.crypto.pseudonymizer.token if deps.crypto else None
        res = decide(
            text, spans, lambda t: deps.learner.sensitivity(org, t), deps.policy, forced, tokenizer
        )
        if deps.crypto:
            used = {
                res.tokens[i]
                for i, d in enumerate(res.decisions)
                if d.action is Action.PSEUDONYMIZE
            }
            for tok in used:
                t, value = res.token_values[tok]
                deps.crypto.vault.put(tok, t, value)
        visible = list(state.get("allowed_values", []))
        for s, d in zip(spans, res.decisions, strict=True):
            if d.action is Action.KEEP:
                visible.append(s.text)
            elif d.action is Action.GENERALIZE:
                visible.append(generalize(s.pii_type, s.text))
        rec = RoundRecord(
            state.get("round", 0), text, tuple(spans), tuple(res.decisions), res.output, res.risk
        )
        return {
            "decisions": res.decisions,
            "risk": res.risk,
            "output": res.output,
            "allowed_values": visible,
            "history": [rec],
            "_info": f"risk {res.risk.level.value}",
        }

    def verify_node(state: GraphState) -> dict[str, Any]:
        """FR-21: a stricter second opinion on the cleaned output."""
        out = state["output"]
        raw = [s for det in deps.detectors.values() for s in det.detect(out)]
        found = fuse(out, raw, deps.verify_threshold)
        leaks = filter_known(out, found, state.get("allowed_values", []))
        return {"leaks": leaks, "_info": f"{len(leaks)} leaks"}

    def route_after_verify(state: GraphState) -> str:
        if state["leaks"] and state.get("round", 0) + 1 < deps.max_rounds:
            return "next_round"
        return "finalize"

    def next_round(state: GraphState) -> dict[str, Any]:
        return {"text": state["output"], "round": state.get("round", 0) + 1}

    def finalize(state: GraphState) -> dict[str, Any]:
        """Risk of the whole document: what round 1 left visible. Later rounds only protect
        more, so this is an upper bound (conservative), never an under-estimate."""
        first = state["history"][0]
        risk = assess(first.text_in, visible_spans(list(first.spans), list(first.decisions)))
        n = state.get("round", 0) + 1
        if deps.crypto:
            counts: dict[str, int] = {}
            for rec in state["history"]:
                for sp, d in zip(rec.spans, rec.decisions, strict=True):
                    k = f"{sp.pii_type.value}:{d.action.value}"
                    counts[k] = counts.get(k, 0) + 1
            deps.crypto.audit.append(
                deps.crypto.actor,
                "scan_completed",
                {
                    "scan": state.get("scan_id", ""),
                    "org": state.get("org", "default"),
                    "rounds": n,
                    "risk": risk.level.value,
                    "unresolved_leaks": len(state.get("leaks", [])),
                    "counts": counts,
                },
            )
        return {"risk": risk, "_info": f"done after {n} round(s), risk {risk.level.value}"}

    g.add_node("fuse", _timed("fuse", fuse_node))
    g.add_node("review", _timed("review", review_gate))
    g.add_node("policy", _timed("policy", policy_node))
    g.add_node("verify", _timed("verify", verify_node))
    g.add_node("next_round", _timed("next_round", next_round))
    g.add_node("finalize", _timed("finalize", finalize))

    for n in names:
        g.add_edge(START, n)
        g.add_edge("next_round", n)
    g.add_edge(names, "fuse")  # fan-in: fuse runs once all detectors finished
    g.add_edge("fuse", "review")
    g.add_edge("review", "policy")
    g.add_edge("policy", "verify")
    g.add_conditional_edges("verify", route_after_verify, ["next_round", "finalize"])
    g.add_edge("finalize", END)

    return g.compile(checkpointer=checkpointer or InMemorySaver(serde=make_serde()))


# ---------- small helpers for callers (API in M5) ----------


def _cfg(thread_id: str) -> Any:
    return {"configurable": {"thread_id": thread_id}}


def start_scan(
    app: CompiledStateGraph[Any, Any, Any, Any], text: str, thread_id: str, org: str = "default"
) -> dict[str, Any]:
    init = {
        "scan_id": thread_id, "org": org, "original": text, "text": text,
        "round": 0, "allowed_values": [],
    }  # fmt: skip
    return dict(app.invoke(init, _cfg(thread_id)))


def resume_scan(
    app: CompiledStateGraph[Any, Any, Any, Any], thread_id: str, answers: list[dict[str, Any]]
) -> dict[str, Any]:
    return dict(app.invoke(Command(resume=answers), _cfg(thread_id)))


def pending_review(state: dict[str, Any]) -> list[dict[str, Any]] | None:
    intr = state.get("__interrupt__")
    return list(intr[0].value["items"]) if intr else None


def result_of(state: dict[str, Any]) -> ScanResult:
    return ScanResult(
        output=state["output"],
        risk=state["risk"],
        rounds=state.get("round", 0) + 1,
        unresolved_leaks=tuple(state.get("leaks", [])),
        history=tuple(state.get("history", [])),
        events=tuple(state.get("events", [])),
    )

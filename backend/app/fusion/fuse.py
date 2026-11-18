"""Source-aware span fusion (FR-11, FR-12, ADR-0013).

Pipeline, each step a small pure function so it can be tested alone:
  clean     -> trim spaces/punctuation, drop keyword words ("Aadhaar") and masked values (XX4521)
  context   -> lower model scores for numbers after "OTP", "order", "room", ... (FR-08)
  threshold -> drop weak spans
  resolve   -> group overlapping spans; validated rules beat model guesses;
               agreeing sources raise confidence (noisy-OR)
  relabel   -> a lone capitalised word tagged ADDRESS ("Bhopal") is a LOCATION
  merge     -> join split addresses ("22, Nehru Nagar"), split IDs ("KL11 2019...")
  expand    -> pull a weekday into a date ("Monday, 16 November 2026")
"""

import re
from dataclasses import replace

from app.detectors.context import context_factor
from app.detectors.types import PiiType, Span

THRESHOLD = 0.5
SOURCE_PRIORITY = {"rules": 2, "context": 1, "ner": 0}
ID_FAMILY = {PiiType.AADHAAR: PiiType.GOV_ID, PiiType.PAN: PiiType.GOV_ID}

STOPWORDS = frozenset(
    {
        "aadhaar", "aadhar", "pan", "ifsc", "passport", "licence", "license", "mobile",
        "phone", "email", "card", "upi", "otp", "dob", "gender", "name", "address",
        "patient", "a/c", "account",
    }
)  # fmt: skip
STREET_WORDS = frozenset(
    {
        "road", "rd", "street", "st", "nagar", "park", "colony", "lane", "marg", "layout",
        "flat", "block", "sector", "avenue", "cross", "apartment", "apartments", "towers",
        "enclave", "vihar", "puram", "house", "floor",
    }
)  # fmt: skip

_MASKED = re.compile(r"[Xx*]{2,}")
_PIN = re.compile(r"\d{6}")
_GAP = re.compile(r"[\s,.\-/]{0,3}")
_SPACE = re.compile(r"\s{1,2}")
_WEEKDAY_BEFORE = re.compile(r"\b(?:mon|tues|wednes|thurs|fri|satur|sun)day,?\s+$", re.IGNORECASE)
_TRIM_CHARS = " \t\n,;:-"


def _respan(text: str, s: Span, start: int, end: int, **changes: object) -> Span:
    return replace(s, start=start, end=end, text=text[start:end], **changes)  # type: ignore[arg-type]


def family(t: PiiType) -> PiiType:
    return ID_FAMILY.get(t, t)


# ---------- clean ----------


def clean(text: str, spans: list[Span]) -> list[Span]:
    out: list[Span] = []
    for s in spans:
        start, end = s.start, s.end
        while start < end and text[start] in _TRIM_CHARS:
            start += 1
        while end > start and text[end - 1] in _TRIM_CHARS:
            end -= 1
        if start >= end:
            continue
        nl = text.find("\n", start, end)
        if nl != -1:  # a PII value never spans lines ("Kozhikode\nPatient"): keep line 1
            end = nl
            while end > start and text[end - 1] in _TRIM_CHARS:
                end -= 1
            if start >= end:
                continue
        value = text[start:end]
        if value.lower().strip(".:") in STOPWORDS or _MASKED.search(value):
            continue
        out.append(_respan(text, s, start, end) if (start, end) != (s.start, s.end) else s)
    return out


# ---------- context ----------


def apply_context(text: str, spans: list[Span]) -> list[Span]:
    """Rules already passed a checksum/format check, so context only adjusts model spans."""
    out: list[Span] = []
    for s in spans:
        if s.source == "rules":
            out.append(s)
            continue
        f = context_factor(text, s)
        out.append(s if f == 1.0 else replace(s, score=round(min(1.0, s.score * f), 4)))
    return out


# ---------- resolve ----------


def _clusters(spans: list[Span]) -> list[list[Span]]:
    """Groups of spans connected by overlap (interval sweep, O(n log n))."""
    groups: list[list[Span]] = []
    end = -1
    for s in sorted(spans, key=lambda x: (x.start, x.end)):
        if groups and s.start < end:
            groups[-1].append(s)
            end = max(end, s.end)
        else:
            groups.append([s])
            end = s.end
    return groups


def _overlaps(a: Span, b: Span) -> bool:
    return a.start < b.end and b.start < a.end


def _noisy_or(scores: list[float]) -> float:
    p = 1.0
    for x in scores:
        p *= 1.0 - x
    return round(1.0 - p, 4)


def resolve(spans: list[Span]) -> list[Span]:
    kept: list[Span] = []
    for group in _clusters(spans):
        ranked = sorted(
            group,
            key=lambda s: (-SOURCE_PRIORITY.get(s.source, 0), -s.score, -(s.end - s.start)),
        )
        chosen: list[Span] = []
        for s in ranked:
            if all(not _overlaps(s, c) for c in chosen):
                chosen.append(s)
        for c in chosen:
            agree = [
                o for o in group if _overlaps(o, c) and family(o.pii_type) == family(c.pii_type)
            ]
            sources = sorted({o.source for o in agree})
            kept.append(
                replace(c, score=_noisy_or([o.score for o in agree]), source="+".join(sources))
            )
    return sorted(kept, key=lambda s: s.start)


# ---------- relabel / merge / expand ----------


def _has_street_word(value: str) -> bool:
    return any(w.lower().strip(".,") in STREET_WORDS for w in value.split())


def relabel(spans: list[Span]) -> list[Span]:
    out: list[Span] = []
    for s in spans:
        v = s.text
        if (
            s.pii_type is PiiType.ADDRESS
            and v.isalpha()
            and v[0].isupper()
            and not _has_street_word(v)
        ):
            out.append(replace(s, pii_type=PiiType.LOCATION))
        else:
            out.append(s)
    return out


def _can_merge(a: Span, b: Span, gap: str) -> PiiType | None:
    """Type of the merged span, or None if a and b must stay apart."""
    if not _GAP.fullmatch(gap):
        return None
    ta, tb = a.pii_type, b.pii_type
    if ta is tb and ta in (PiiType.GOV_ID, PiiType.PERSON):
        return ta if _SPACE.fullmatch(gap) else None
    if {ta, tb} <= {PiiType.ADDRESS, PiiType.LOCATION} and PiiType.ADDRESS in (ta, tb):
        if ta is tb:
            return PiiType.ADDRESS
        loc, addr = (a, b) if ta is PiiType.LOCATION else (b, a)
        if _PIN.fullmatch(addr.text):
            return None  # "Kochi 682016": city and PIN stay apart
        if _has_street_word(loc.text) or _SPACE.fullmatch(gap):
            return PiiType.ADDRESS  # "Green Park", "Nehru Nagar"
    return None


def merge(text: str, spans: list[Span]) -> list[Span]:
    cur = sorted(spans, key=lambda s: s.start)
    changed = True
    while changed:  # repeat until nothing merges (pieces can chain)
        changed = False
        out: list[Span] = []
        for s in cur:
            if out and s.start >= out[-1].end:
                p = out[-1]
                t = _can_merge(p, s, text[p.end : s.start])
                if t is not None:
                    src = "+".join(sorted(set(p.source.split("+")) | set(s.source.split("+"))))
                    out[-1] = _respan(
                        text, p, p.start, s.end, pii_type=t, score=max(p.score, s.score), source=src
                    )
                    changed = True
                    continue
            out.append(s)
        cur = out
    return cur


def expand_dates(text: str, spans: list[Span]) -> list[Span]:
    out: list[Span] = []
    for s in spans:
        m = _WEEKDAY_BEFORE.search(text[: s.start]) if s.pii_type is PiiType.DATE else None
        out.append(_respan(text, s, m.start(), s.end) if m else s)
    return out


# ---------- pipeline ----------


def fuse(text: str, spans: list[Span], threshold: float = THRESHOLD) -> list[Span]:
    s = clean(text, spans)
    s = apply_context(text, s)
    s = [x for x in s if x.score >= threshold]
    s = resolve(s)
    s = relabel(s)
    s = merge(text, s)
    return expand_dates(text, s)

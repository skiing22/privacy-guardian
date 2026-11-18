"""Actions on one span (FR-19): how each one changes the text."""

import re
from enum import StrEnum

from app.detectors.types import PiiType


class Action(StrEnum):
    KEEP = "keep"
    GENERALIZE = "generalize"  # age 34 -> 30-34, DOB -> year, PIN 682016 -> 682XXX
    MASK = "mask"  # 98470 12345 -> 98*** ***45
    PSEUDONYMIZE = "pseudonymize"  # Rahul Sharma -> PERSON_1 (HMAC token in M4)
    REDACT = "redact"  # -> [REDACTED]


# How much privacy each action buys (0..1) and how much usefulness it costs (0..1).
PRIVACY_GAIN = {
    Action.KEEP: 0.0, Action.GENERALIZE: 0.6, Action.MASK: 0.7,
    Action.PSEUDONYMIZE: 0.9, Action.REDACT: 1.0,
}  # fmt: skip
USEFULNESS_LOSS = {
    Action.KEEP: 0.0, Action.GENERALIZE: 0.2, Action.MASK: 0.4,
    Action.PSEUDONYMIZE: 0.3, Action.REDACT: 1.0,
}  # fmt: skip

_MASKABLE = {
    PiiType.PHONE, PiiType.CARD, PiiType.AADHAAR, PiiType.PAN, PiiType.GOV_ID,
    PiiType.EMAIL, PiiType.IFSC, PiiType.IP_ADDRESS,
}  # fmt: skip
_PSEUDONYMIZABLE = _MASKABLE | {PiiType.PERSON, PiiType.ORG, PiiType.LOCATION, PiiType.ADDRESS}
_PIN = re.compile(r"\d{6}")
_NUM = re.compile(r"\d+")
_YEAR = re.compile(r"(?:19|20)\d{2}")


def can_generalize(t: PiiType, value: str) -> bool:
    v = value.strip()
    if t is PiiType.AGE:
        return bool(_NUM.fullmatch(v))
    if t is PiiType.DATE:
        return bool(_YEAR.search(v))
    if t is PiiType.ADDRESS:
        return bool(_PIN.fullmatch(v))
    return False


_GENERALIZABLE = {PiiType.AGE, PiiType.DATE, PiiType.ADDRESS}


def actions_for_type(t: PiiType) -> list[Action]:
    """Actions an admin may fix for a type (API 4.13), weakest first. Value-specific limits
    still apply per item: a fixed "generalize" on a value that cannot be generalized
    falls back to redact (utility.choose)."""
    acts = [Action.KEEP]
    if t in _GENERALIZABLE:
        acts.append(Action.GENERALIZE)
    if t in _MASKABLE:
        acts.append(Action.MASK)
    if t in _PSEUDONYMIZABLE:
        acts.append(Action.PSEUDONYMIZE)
    acts.append(Action.REDACT)
    return acts


def allowed(t: PiiType, value: str) -> list[Action]:
    """Actions that make sense for this type and value, weakest first."""
    acts = [Action.KEEP]
    if can_generalize(t, value):
        acts.append(Action.GENERALIZE)
    if t in _MASKABLE:
        acts.append(Action.MASK)
    if t in _PSEUDONYMIZABLE:
        acts.append(Action.PSEUDONYMIZE)
    acts.append(Action.REDACT)
    return acts


def generalize(t: PiiType, value: str) -> str:
    v = value.strip()
    if t is PiiType.AGE:
        lo = int(v) // 5 * 5
        return f"{lo}-{lo + 4}"
    if t is PiiType.DATE:
        m = _YEAR.search(v)
        assert m is not None
        return m.group()
    if t is PiiType.ADDRESS:
        return v[:3] + "XXX"
    raise ValueError(f"cannot generalize {t}")


def mask(t: PiiType, value: str) -> str:
    """Hide digits/letters but keep separators and a few edge characters."""
    if t is PiiType.EMAIL and "@" in value:
        user, domain = value.split("@", 1)
        return user[:1] + "*" * max(1, len(user) - 1) + "@" + domain
    keep_end = 4 if t in (PiiType.CARD, PiiType.AADHAAR, PiiType.PAN, PiiType.GOV_ID) else 2
    keep_start = 2 if t is PiiType.PHONE else 0
    idx = [i for i, c in enumerate(value) if c.isalnum()]
    hide = set(idx[keep_start : max(keep_start, len(idx) - keep_end)])
    return "".join(
        ("X" if t is not PiiType.PHONE else "*") if i in hide else c for i, c in enumerate(value)
    )


def render(action: Action, t: PiiType, value: str, token: str) -> str:
    if action is Action.KEEP:
        return value
    if action is Action.GENERALIZE:
        return generalize(t, value)
    if action is Action.MASK:
        return mask(t, value)
    if action is Action.PSEUDONYMIZE:
        return token
    return "[REDACTED]"

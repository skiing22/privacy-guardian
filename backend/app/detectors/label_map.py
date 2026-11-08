"""Map ai4privacy labels to our PiiType and merge split entities (ADR-0010).

ai4privacy labels a name as GIVENNAME + SURNAME and an address as STREET + BUILDINGNUM +
ZIPCODE. We want one PERSON / one ADDRESS span, so neighbours of the same type that are
separated only by a short run of spaces or light punctuation are merged.
"""

import re

from app.detectors.types import PiiType

AI4PRIVACY_MAP: dict[str, PiiType | None] = {
    "GIVENNAME": PiiType.PERSON,
    "SURNAME": PiiType.PERSON,
    "CITY": PiiType.LOCATION,
    "STREET": PiiType.ADDRESS,
    "BUILDINGNUM": PiiType.ADDRESS,
    "ZIPCODE": PiiType.ADDRESS,
    "TELEPHONENUM": PiiType.PHONE,
    "EMAIL": PiiType.EMAIL,
    "DATE": PiiType.DATE,
    "CREDITCARDNUMBER": PiiType.CARD,
    "IDCARDNUM": PiiType.GOV_ID,
    "PASSPORTNUM": PiiType.GOV_ID,
    "DRIVERLICENSENUM": PiiType.GOV_ID,
    "SOCIALNUM": PiiType.GOV_ID,
    "TAXNUM": PiiType.GOV_ID,
    "AGE": PiiType.AGE,
    "GENDER": PiiType.GENDER,
    "SEX": PiiType.GENDER,
    "TITLE": None,  # "Mr.", "Dr." alone identify no one
    "TIME": None,
}

MERGEABLE = frozenset({PiiType.PERSON, PiiType.ADDRESS})
_GAP = re.compile(r"[\s,.\-/]{0,3}")  # what may sit between two parts of one entity

RawSpan = tuple[int, int, str]
MappedSpan = tuple[int, int, PiiType]


def map_spans(text: str, spans: list[RawSpan]) -> list[MappedSpan]:
    """Map labels, drop unwanted ones, merge neighbours. Unknown labels raise KeyError
    on purpose, so a new dataset version cannot silently lose a PII type."""
    mapped: list[MappedSpan] = []
    for start, end, label in sorted(spans):
        t = AI4PRIVACY_MAP[label]
        if t is not None:
            mapped.append((start, end, t))

    merged: list[MappedSpan] = []
    for start, end, t in mapped:
        if merged:
            p_start, p_end, p_t = merged[-1]
            if t == p_t and t in MERGEABLE and start >= p_end and _GAP.fullmatch(text[p_end:start]):
                merged[-1] = (p_start, end, t)
                continue
        merged.append((start, end, t))
    return merged

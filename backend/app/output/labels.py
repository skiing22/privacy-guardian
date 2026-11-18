"""Plain-language labels shared by the API and the report (DESIGN 2.2, 5.7, 13)."""

from app.detectors.types import PiiType
from app.policy.actions import Action

FAMILY: dict[PiiType, str] = {
    **dict.fromkeys((PiiType.PERSON, PiiType.AGE, PiiType.GENDER), "identity"),
    **dict.fromkeys(
        (PiiType.PHONE, PiiType.EMAIL, PiiType.ADDRESS, PiiType.LOCATION, PiiType.IP_ADDRESS),
        "contact",
    ),
    **dict.fromkeys(
        (PiiType.AADHAAR, PiiType.PAN, PiiType.CARD, PiiType.IFSC, PiiType.GOV_ID), "id"
    ),
    **dict.fromkeys((PiiType.DATE, PiiType.ORG), "other"),
}

ACTION_LABEL: dict[Action, str] = {
    Action.KEEP: "Keep",
    Action.GENERALIZE: "Generalize",
    Action.MASK: "Mask",
    Action.PSEUDONYMIZE: "Replace with token",
    Action.REDACT: "Remove",
}

REASON_TEXT: dict[str, str] = {
    "utility": "Best balance of privacy and usefulness for this type.",
    "override": "Fixed by an admin rule for this type.",
    "review": "Chosen by you during review.",
    "risk": "Hidden more to lower the chance of identifying someone.",
    "business number": "Looks like a public business number, so it stays visible.",
}
LATER_ROUND_TEXT = "Missed at first and caught by the leak check."

STEP_LABEL = {
    0: "Waiting to start",
    1: "Reading file",
    2: "Finding personal data",
    3: "Combining results",
    4: "Choosing what to hide",
    5: "Checking for leaks",
}

EVENT_LABEL = {
    "scan_completed": "Scan finished",
    "review": "Review answered",
    "reidentify": "Real value shown",
    "reidentify_denied": "Reveal refused",
    "rules_changed": "Rules changed",
    "beliefs_reset": "Learning reset",
    "retention": "Old data deleted",
    "user_created": "User added",
    "user_disabled": "User disabled",
    "anchor_saved": "Anchor saved",
}

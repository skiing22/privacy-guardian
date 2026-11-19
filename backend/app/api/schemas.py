"""Request and response models (API 4). Requests forbid unknown fields (API 2.1);
the OpenAPI schema built from these is the frontend's contract."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.detectors.types import PiiType
from app.policy.actions import Action

ScanStatus = Literal["queued", "running", "needs_review", "done", "failed"]
RiskLevelName = Literal["LOW", "MEDIUM", "HIGH", "DIRECT"]
Family = Literal["identity", "contact", "id", "other"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- requests ----


class LoginIn(Strict):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v[1:]:
            raise ValueError("Enter a valid email address.")
        return v


class AnswerIn(Strict):
    index: int = Field(ge=0)
    verdict: Literal["protect", "keep", "not_pii"]
    pii_type: PiiType | None = None


class AnswersIn(Strict):
    answers: list[AnswerIn] = Field(min_length=1, max_length=500)


class RuleIn(Strict):
    pii_type: PiiType
    action: Action | None


class RulesIn(Strict):
    rules: list[RuleIn] = Field(max_length=len(PiiType))


class RevealIn(Strict):
    token: str = Field(pattern=r"^[A-Z_]+_[0-9a-f]{6,64}$", max_length=80)
    reason: str = Field(max_length=500)

    @field_validator("reason")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip()


class ConfirmIn(Strict):
    confirm: Literal[True]


# ---- responses ----


class Health(BaseModel):
    status: Literal["ok", "starting"]
    model_ready: bool
    version: str


class Me(BaseModel):
    id: int
    email: str
    role: Literal["user", "admin"]


class ScanAccepted(BaseModel):
    id: str
    status: ScanStatus
    poll_url: str | None = None


class ScanListItem(BaseModel):
    id: str
    filename: str
    format: str
    status: ScanStatus
    risk_level: RiskLevelName | None
    created_at: str
    expires_at: str


class ScanList(BaseModel):
    items: list[ScanListItem]
    next_cursor: str | None


class Risk(BaseModel):
    level: RiskLevelName
    est_matches: float
    clues: list[str]
    unresolved_leaks: int


class Context(BaseModel):
    before: str
    text: str
    after: str


class ReviewItem(BaseModel):
    index: int
    pii_type: PiiType
    family: Family
    score: float
    reason: str
    context: Context


class Review(BaseModel):
    items: list[ReviewItem]


class ScanError(BaseModel):
    code: str
    message: str
    step: int


class ScanStatusOut(BaseModel):
    id: str
    filename: str
    format: str
    status: ScanStatus
    step: int
    step_label: str
    round: int
    max_rounds: int
    created_at: str
    updated_at: str
    finished_at: str | None
    expires_at: str
    review: Review | None
    risk: Risk | None
    error: ScanError | None


class ResultItem(BaseModel):
    idx: int
    round: int
    start: int
    end: int
    pii_type: PiiType
    family: Family
    score: float
    sources: list[str]
    action: Action
    action_label: str
    reason: str
    reason_text: str
    token: str | None
    output: str


class Segment(BaseModel):
    text: str
    item_idx: int | None


class ScanResult(BaseModel):
    id: str
    rounds: int
    risk: Risk | None
    original_text: str
    items: list[ResultItem]
    cleaned_segments: list[Segment]


class RuleOut(BaseModel):
    pii_type: PiiType
    family: Family
    action: Action | None
    allowed_actions: list[Action]
    updated_at: str | None


class RulesOut(BaseModel):
    rules: list[RuleOut]


class RevealOut(BaseModel):
    token: str
    pii_type: PiiType | None
    value: str
    logged_as: int | None


class Actor(BaseModel):
    type: Literal["user", "system"]
    id: int | None
    email: str | None


class AuditItem(BaseModel):
    seq: int
    ts: str
    actor: Actor
    event: str
    event_label: str
    details: dict[str, Any]


class AuditPage(BaseModel):
    items: list[AuditItem]
    next_before_seq: int | None


class AnchorInfo(BaseModel):
    seq: int
    saved_at: str


class VerifyOut(BaseModel):
    ok: bool
    checked: int
    first_bad_seq: int | None
    reason: str | None
    anchor: AnchorInfo | None


class AnchorOut(BaseModel):
    seq: int
    mac_prefix: str
    saved_at: str


class ErrorBody(BaseModel):
    code: str
    message: str
    field: str | None
    request_id: str | None


class ErrorOut(BaseModel):
    error: ErrorBody

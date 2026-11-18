"""Endpoints 13-19: admin (API 4.13 to 4.19). Every route needs role admin, except
reveal, which lets the domain refuse and log non-admins (reidentify_denied)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import Admin, Box, User
from app.api.schemas import (
    AnchorOut,
    AuditPage,
    ConfirmIn,
    ErrorOut,
    RevealIn,
    RevealOut,
    RulesIn,
    RulesOut,
    VerifyOut,
)
from app.services.admin import AdminService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={401: {"model": ErrorOut}, 403: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)


@router.get("/rules")
def get_rules(admin: Admin, c: Box) -> RulesOut:
    return RulesOut.model_validate(AdminService(c, admin).get_rules())


@router.put("/rules")
def put_rules(body: RulesIn, admin: Admin, c: Box) -> RulesOut:
    rules = [(r.pii_type, r.action) for r in body.rules]
    return RulesOut.model_validate(AdminService(c, admin).put_rules(rules))


@router.post("/reveal", responses={404: {"model": ErrorOut}, 429: {"model": ErrorOut}})
def reveal(body: RevealIn, user: User, c: Box) -> RevealOut:
    return RevealOut.model_validate(AdminService(c, user).reveal(body.token, body.reason))


@router.post("/beliefs/reset", status_code=204)
def reset_beliefs(body: ConfirmIn, admin: Admin, c: Box) -> None:
    AdminService(c, admin).reset_beliefs()


@router.get("/audit")
def audit(
    admin: Admin,
    c: Box,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_seq: Annotated[int | None, Query(ge=0)] = None,
) -> AuditPage:
    return AuditPage.model_validate(AdminService(c, admin).audit_page(before_seq, limit))


@router.post("/audit/verify")
def verify(admin: Admin, c: Box) -> VerifyOut:
    return VerifyOut.model_validate(AdminService(c, admin).verify())


@router.post("/audit/anchor")
def anchor(admin: Admin, c: Box) -> AnchorOut:
    return AnchorOut.model_validate(AdminService(c, admin).save_anchor())

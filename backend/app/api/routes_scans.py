"""Endpoints 5-12: scans (API 4.5 to 4.12). Owner scoping lives in the service/storage."""

from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile

from app.api.deps import GENERAL_LIMIT, Box, User, UserNoLimit
from app.api.schemas import (
    AnswersIn,
    ErrorOut,
    ScanAccepted,
    ScanList,
    ScanResult,
    ScanStatus,
    ScanStatusOut,
)
from app.services.errors import AppError
from app.services.scans import ScanService

router = APIRouter(
    prefix="/scans",
    tags=["scans"],
    responses={401: {"model": ErrorOut}, 404: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
CHUNK = 1024 * 1024


def _read_limited(f: UploadFile, limit: int, mb: int) -> bytes:
    """Read at most `limit` bytes; stop as soon as the file is bigger (API 4.5)."""
    out = bytearray()
    while chunk := f.file.read(CHUNK):
        out += chunk
        if len(out) > limit:
            raise AppError("file_too_large", field="file", mb=mb)
    return bytes(out)


@router.post("", status_code=202, responses={413: {"model": ErrorOut}, 415: {"model": ErrorOut},
                                              429: {"model": ErrorOut}})  # fmt: skip
def create_scan(
    user: User,
    c: Box,
    file: Annotated[UploadFile | None, File()] = None,
    text: Annotated[str | None, Form(max_length=200_000 * 2)] = None,
) -> ScanAccepted:
    data = None
    if file is not None:
        data = _read_limited(file, c.settings.max_upload_bytes, c.settings.max_upload_mb)
    s = ScanService(c, user).create(file.filename if file else None, data, text)
    return ScanAccepted(id=s.id, status=s.status, poll_url=f"/api/v1/scans/{s.id}")


@router.get("")
def list_scans(
    user: User,
    c: Box,
    status: ScanStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> ScanList:
    return ScanList.model_validate(ScanService(c, user).page(status, cursor, limit))


@router.get("/{scan_id}")
def get_scan(scan_id: str, request: Request, user: UserNoLimit, c: Box) -> ScanStatusOut:
    svc = ScanService(c, user)
    if not svc.is_open(scan_id):  # polling an open scan is exempt from the general limit
        c.limiter.hit(f"general:{request.state.session_key}", *GENERAL_LIMIT)
    return ScanStatusOut.model_validate(svc.status(scan_id))


@router.post("/{scan_id}/answers", status_code=202, responses={409: {"model": ErrorOut}})
def answer(scan_id: str, body: AnswersIn, user: User, c: Box) -> ScanAccepted:
    answers = [a.model_dump(mode="json") for a in body.answers]
    s = ScanService(c, user).answer(scan_id, answers)
    return ScanAccepted(id=s.id, status=s.status)


@router.get("/{scan_id}/result", responses={409: {"model": ErrorOut}})
def result(scan_id: str, user: User, c: Box) -> ScanResult:
    return ScanResult.model_validate(ScanService(c, user).result(scan_id))


@router.get(
    "/{scan_id}/download",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}, 409: {"model": ErrorOut}},
)
def download(
    scan_id: str, user: User, c: Box, kind: Literal["cleaned", "report"] = "cleaned"
) -> Response:
    d = ScanService(c, user).download(scan_id, kind)
    return Response(
        d.data,
        media_type=d.content_type,
        headers={"Content-Disposition": f'attachment; filename="{d.filename}"'},
    )


@router.post("/{scan_id}/retry", status_code=202, responses={409: {"model": ErrorOut}})
def retry(scan_id: str, user: User, c: Box) -> ScanAccepted:
    s = ScanService(c, user).retry(scan_id)
    return ScanAccepted(id=s.id, status=s.status)


@router.delete("/{scan_id}", status_code=204, responses={409: {"model": ErrorOut}})
def delete(scan_id: str, user: User, c: Box) -> None:
    ScanService(c, user).delete(scan_id)

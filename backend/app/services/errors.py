"""Application errors with stable codes (API 2.3, 2.4). The API layer turns them into the
JSON error body; messages are safe to show and never contain document data."""

MESSAGES: dict[str, tuple[int, str]] = {
    "bad_origin": (400, "Request blocked."),
    "auth_required": (401, "Please log in."),
    "auth_failed": (401, "Wrong email or password."),
    "session_expired": (401, "Please log in again."),
    "forbidden": (403, "Only admins can do this."),
    "not_found": (404, "Not found."),
    "unknown_token": (404, "Unknown token."),
    "not_waiting_for_review": (409, "This scan is not waiting for answers."),
    "scan_not_done": (409, "This scan has not finished yet."),
    "scan_running": (409, "This scan is still running."),
    "scan_not_failed": (409, "Only failed scans can be retried."),
    "file_too_large": (413, "File too large (max {mb} MB)."),
    "unsupported_type": (415, "Only TXT, PDF, DOCX and CSV files are supported."),
    "invalid_request": (422, "Check the highlighted field."),
    "empty_input": (422, "Add a file or paste some text."),
    "pdf_no_text": (422, "This PDF has no text (scanned image). Not supported yet."),
    "file_unreadable": (422, "This file could not be read."),
    "invalid_answers": (422, "Answer every item once."),
    "action_not_allowed": (422, "That action is not available for this type."),
    "reason_too_short": (422, "Reason must be at least 10 characters."),
    "vault_integrity": (422, "Vault entry failed integrity check."),
    "rate_limited": (429, "Too many tries. Wait {n} seconds."),
    "model_not_ready": (503, "Preparing the model."),
    "busy": (503, "Service busy. Try again shortly."),
    "storage_unavailable": (503, "Service unavailable. Try again shortly."),
    "internal": (500, "Something went wrong. Quote request {request_id}."),
}


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        field: str | None = None,
        headers: dict[str, str] | None = None,
        **fmt: object,
    ) -> None:
        status, default = MESSAGES[code]
        self.code, self.status, self.field = code, status, field
        self.message = message or (default.format(**fmt) if fmt else default)
        self.headers = headers or {}
        super().__init__(code)


def storage_error_code(exc: BaseException) -> str | None:
    """Map low-level storage failures to API codes: a locked database -> busy (503),
    other database or disk failures -> storage_unavailable (503)."""
    from sqlalchemy.exc import OperationalError

    if isinstance(exc, OperationalError):
        text = str(exc.orig).lower()
        return "busy" if "locked" in text or "busy" in text else "storage_unavailable"
    if isinstance(exc, OSError):
        return "storage_unavailable"
    return None

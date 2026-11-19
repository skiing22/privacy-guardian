"""Cheap upload checks done before a scan is queued (API 4.5). Deep checks (a PDF's text
layer, a readable DOCX) happen in the worker's parse step."""

import io
import re
import unicodedata
import zipfile
from pathlib import PurePath

EXTENSIONS = {".txt": "txt", ".md": "md", ".pdf": "pdf", ".docx": "docx", ".csv": "csv"}
DOCX_MAX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
PASTED_NAME = "pasted-text.txt"


class UploadRejectedError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code  # unsupported_type | empty_input | file_unreadable | text_too_long


def clean_filename(name: str) -> str:
    """Base name only, no control characters, at most 255 characters."""
    base = PurePath(name.replace("\\", "/")).name
    base = "".join(c for c in base if unicodedata.category(c)[0] != "C").strip()
    if len(base) > 255:
        stem, dot, ext = base.rpartition(".")
        base = (stem[: 255 - len(ext) - 1] + dot + ext) if dot else base[:255]
    return base or "file"


def format_of(filename: str) -> str:
    fmt = EXTENSIONS.get(PurePath(filename).suffix.lower())
    if fmt is None:
        raise UploadRejectedError("unsupported_type")
    return fmt


def _is_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    for enc in ("utf-8", "cp1252"):
        try:
            data.decode(enc)
            return True
        except UnicodeDecodeError:
            continue
    return False


_DOC_XML = re.compile(r"^word/document\d*\.xml$")


def check_upload(filename: str, data: bytes) -> str:
    """Returns the format, or raises UploadRejectedError."""
    fmt = format_of(filename)
    if not data:
        raise UploadRejectedError("empty_input")
    if fmt == "pdf":
        if not data.startswith(b"%PDF-"):
            raise UploadRejectedError("unsupported_type")
    elif fmt == "docx":
        if not data.startswith(b"PK\x03\x04"):
            raise UploadRejectedError("unsupported_type")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                infos = z.infolist()
        except zipfile.BadZipFile as e:
            raise UploadRejectedError("file_unreadable") from e
        if sum(i.file_size for i in infos) > DOCX_MAX_UNCOMPRESSED:
            raise UploadRejectedError("file_unreadable")  # zip bomb
        if not any(_DOC_XML.match(i.filename) for i in infos):
            raise UploadRejectedError("unsupported_type")
    elif not _is_text(data):
        raise UploadRejectedError("unsupported_type")
    return fmt


def check_text(text: str) -> bytes:
    t = text.strip()
    if not t:
        raise UploadRejectedError("empty_input")
    if len(t) > MAX_TEXT_CHARS:
        raise UploadRejectedError("text_too_long")
    return t.encode()

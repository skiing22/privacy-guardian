"""Time helpers: one format everywhere (DATABASE 1.1). Tests replace `now`."""

from datetime import UTC, datetime, timedelta

ISO = "%Y-%m-%dT%H:%M:%S.%fZ"


def now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


__all__ = ["iso", "now", "parse", "timedelta"]

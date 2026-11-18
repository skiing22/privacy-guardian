"""Retention job (FR-34, DATABASE 10.3): runs at startup and then every 24 hours.

Deletes expired scans (rows cascade to files meta and decisions), their encrypted files
and checkpoints; expired sessions; vault rows no decision uses any more (only if older
than a day, so a scan still being written never loses its entries); orphan files.
Writes one `retention` audit record with counts only.
"""

import logging

from app.services import clock
from app.services.container import Container
from app.storage.repos import SessionRepo
from app.storage.worker_repo import WorkerRepo

log = logging.getLogger("app.retention")


def run_retention(c: Container) -> dict[str, int]:
    w = WorkerRepo(c.db)
    now = clock.now()
    expired = w.expired_ids(clock.iso(now))
    for sid in expired:
        w.delete_scan(sid)
        c.files.delete_scan(sid)
        c.saver.delete_thread(sid)
    sessions = SessionRepo(c.db).delete_expired(clock.iso(now))
    vault = w.delete_unused_vault(None, clock.iso(now - clock.timedelta(days=1)))
    known = w.all_ids()
    orphans = [sid for sid in c.files.scan_ids(min_age_s=3600) if sid not in known]
    for sid in orphans:
        c.files.delete_scan(sid)
    counts = {"scans": len(expired), "sessions": sessions, "vault": vault, "files": len(orphans)}
    if any(counts.values()):
        c.crypto.audit.append("system", "retention", counts)
    log.info("retention done", extra={"event": "retention", "count": sum(counts.values())})
    return counts

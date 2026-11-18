# Runbook: backup and restore

All commands run inside the app container (`docker compose exec app ...`).

## Backup (daily, and before every upgrade)

```sh
python -m app.manage backup /backups/$(date +%F)
```

Writes a consistent copy of `app.db` and `checkpoints.db` (SQLite online backup, safe while
the app runs) and the encrypted `files/` folder. Copy `/backups` off the server.

Keep `audit.anchor.json` **somewhere else** than the backups (DATABASE 11), otherwise a
tampered backup could come with a matching anchor.

Keys are not in the backup. Without the same `PG_*_KEY` values, files, vault entries and
checkpoints cannot be read. Store the keys in your secret manager, never next to backups.

## Restore

1. Stop the app: `docker compose stop app`.
2. Move the broken data aside: `mv /data /data.broken` (keep it until you are sure).
3. Copy the backup in: `cp -r /backups/2026-11-19 /data` and `chown -R 10001:10001 /data`.
4. Copy the off-server anchor back to `/data/audit.anchor.json`.
5. Start the app with the **same keys**: `docker compose start app`. Startup migrates if the
   backup is from an older version (and backs it up first to `/data/backups/`).
6. Check: `python -m app.manage audit-verify`. Records added after the backup are gone, so
   the anchor may say the log is shorter than anchored. That is the expected result of a
   restore: write it down, then save a new anchor in the admin screen.
7. Open `/health` and log in.

Tested by `backend/tests/test_manage.py::test_restore_from_backup`.

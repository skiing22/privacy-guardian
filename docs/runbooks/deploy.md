# Runbook: deploy to production (P20, D13)

One VM runs `docker compose` with the app, Caddy for HTTPS (ADR-0025, **Proposed**) and one
data volume. Commands run on the VM in the repo folder unless they say otherwise.
`dc` below means `docker compose -f docker-compose.yml -f docker-compose.prod.yml`.

## Owner decisions first (👤)

| Item | Needed | Status |
| --- | --- | --- |
| ADR-0025 (Caddy for HTTPS) | Approve, or pick another TLS option | Proposed |
| VM provider and plan (D13, P20.1) | 2 GB RAM minimum (app uses 1-1.5 GB), 1-2 vCPU, 20 GB disk, Ubuntu 24.04 LTS | Open |
| Domain | A DNS A record pointing at the VM's public IP | Open |
| Off-server place for backups and the audit anchor (DATABASE 10.2, 11) | Two different places | Open |

## 1. Prepare the VM (once)

1. Firewall: allow inbound 22 (SSH, your IP only if you can), 80 and 443. Nothing else.
2. Install Docker Engine and the compose plugin (docs.docker.com/engine/install/ubuntu).
3. `git clone https://github.com/skiing22/privacy-guardian && cd privacy-guardian`
4. `git checkout vX.Y.Z` (a release tag on `main`, ARCHITECTURE 16.2).
5. `mkdir -p backups && sudo chown 10001:10001 backups` (the app runs as uid 10001).

## 2. Secrets and settings (once; never in git)

1. Model token: `mkdir -p .secrets && chmod 700 .secrets`, then put the read-only Hugging
   Face token in `.secrets/hf_token` (`chmod 600`). Build time only (API 8.2).
2. `cp .env.example .env && chmod 600 .env`, then set:

| Variable | Value |
| --- | --- |
| `DOMAIN` | e.g. `pg.example.org` (sets `PUBLIC_ORIGIN=https://…` and `ENV=prod` via the prod file) |
| `PG_TOKEN_KEY`, `PG_AUDIT_KEY`, `PG_VAULT_KEY`, `PG_STORAGE_KEY` | Four **different** new keys, each from `python3 -c "import secrets; print(secrets.token_hex(32))"`. Never the DEV keys (startup refuses them) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | First admin; password 12+ characters. **Delete both lines after the first start** |
| `MODEL_SOURCE`, `MODEL_REPO`, `MODEL_REVISION`, `MODEL_SHA256` | `hf`, the private model repo, its commit hash, the manifest hash (API 8.2) |
| Others | Leave the defaults (`RETENTION_DAYS=7`, `MAX_UPLOAD_MB=10`, …) unless the PRD changes |

3. Copy the four keys into your password manager **now**. Without them, files, vault entries
   and checkpoints in every backup are unreadable (backup-restore runbook).

## 3. Build and start

```sh
dc build            # fails on purpose if the model hash does not match
dc up -d
dc ps               # app becomes "healthy" once the model loads (up to ~2 min)
```

Startup migrates the database (backing it up first to `/data/backups/pre-migrate.db`),
creates the first admin if no users exist, and starts the worker and the retention job.
Then remove `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env` and run `dc up -d` again.

## 4. Verify (P20.5)

Run from your own computer, not the VM:

```sh
B=https://pg.example.org
curl -s $B/health                                    # {"status":"ok","model_ready":true,…}
curl -sI $B/ | grep -iE 'strict-transport|content-security|x-content-type|referrer'
curl -s -o /dev/null -w '%{http_code}\n' http://pg.example.org/   # 308 to https
curl -s -o /dev/null -w '%{http_code}\n' $B:8000/ --max-time 5      # must fail: app port closed
scripts/smoke.sh $B 'admin@…' "$ADMIN_PW"            # read the password from a prompt, not history
```

Also check in a browser: log in, the cookie is `Secure; HttpOnly; SameSite=Strict`; run J1-J5
(PRD); `/docs` shows the app, not Swagger. Record the result in `docs/results/`.

## 5. Daily backup (P20.4)

VM crontab (`crontab -e`), 02:30 every day, keeps 7 days (DATABASE 10.2):

```cron
30 2 * * * cd /home/USER/privacy-guardian && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T app python -m app.manage backup /backups/$(date +\%F) && find backups -mindepth 1 -maxdepth 1 -mtime +7 -exec rm -rf {} +
```

Then copy `backups/` to the off-server place (for example `rsync` from another machine).
After saving an anchor in the admin screen, copy `/data/audit.anchor.json` to a **different**
off-server place: `dc cp app:/data/audit.anchor.json ./anchor-$(date +%F).json`, move it off,
delete the local copy. Restore: `docs/runbooks/backup-restore.md`.

## 6. Upgrade and roll back

```sh
dc exec -T app python -m app.manage backup /backups/pre-$(date +%F)   # before every release
git fetch --tags && git checkout vX.Y.Z
dc build && dc up -d                                                    # migrates on start
```

Roll back: `git checkout` the previous tag, `dc build && dc up -d`. If the release changed the
database (a new file in `backend/app/migrations/versions/`), restore the pre-release backup
first (backup-restore runbook); never run an older image on a newer database.

## Never

- Commit `.env`, `.secrets/` or `backups/` (all git-ignored), or paste keys into chat or logs.
- Run prod with only `docker-compose.yml`: it serves plain HTTP on port 8000 and, unless
  `.env` says otherwise, `ENV=dev` with the public DEV keys.
- Delete the `app-data` volume (`dc down -v`): that is all user data.

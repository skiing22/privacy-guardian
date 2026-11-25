# Deployment preparation check, 2026-11-26 (P20)

Code: `main` at `1e700fa` (after PR #26). Run: Uvicorn started the way the image starts it
(`uvicorn app.main:app`, one worker), `ENV=prod`, fresh temporary data folder, no model
(health stays `starting`, which is enough for these checks). Not a live host.

## Startup refuses unsafe prod config

| Config | Result |
| --- | --- |
| No keys | Refused (missing keys) |
| The four DEV keys | Refused (DEV keys are not allowed in prod) |
| One key used for two purposes | Refused |
| A key shorter than 32 bytes | Refused |
| `PUBLIC_ORIGIN=http://…` | Refused (must be https://) |
| `ADMIN_PASSWORD` under 12 characters | Refused |
| Four new keys, https origin | Starts |

The refusal log holds the error type and text only; the reused key's value did not appear.

## Running prod app

| Check | Result |
| --- | --- |
| `/health` while the model loads | `503`, `model_ready: false` (the container health check waits) |
| Headers on `/` | HSTS `max-age=31536000`, CSP, `nosniff`, `no-referrer` |
| Login cookie | `HttpOnly; Secure; SameSite=strict; Path=/` |
| Login with a foreign `Origin` | `400 bad_origin` |
| CORS headers for a foreign origin | None |
| `/docs`, `/openapi.json` | The SPA page, not Swagger or the schema |
| Admin password in the log | Not present |

## Database

| Check | Result |
| --- | --- |
| Migrations | One revision, `0001_initial` (head); empty database upgrades at startup |
| Restart on existing data | `pre-migrate.db` backup written first; data kept; still 1 user (no second admin) |
| `python -m app.manage backup` | `app.db`, `checkpoints.db`, `files/` written |
| `python -m app.manage audit-verify` | OK |

## Compose files

`docker compose -f docker-compose.yml -f docker-compose.prod.yml config` merges cleanly:
`ENV=prod`, `PUBLIC_ORIGIN=https://$DOMAIN`, app port not published, only Caddy on 80/443;
it stops with a clear error if `DOMAIN` is missing. The base file alone is unchanged.

## Not checked here

- The image build and Caddy itself (this workspace cannot pull from Docker Hub or download
  from GitHub releases). CI builds the image on every push to `main`.
- Anything on a live host: real certificate, DNS, memory use with the real model, J1-J5.

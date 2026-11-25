# ADR-0025: HTTPS on the VM with Caddy in the production compose file

- Status: Proposed (needs owner approval: adds a second container to ARCHITECTURE 16.2)
- Date: 2026-11-26
- Requirements: NFR-04, P20.3; API.md 2.2, 3.1, 7, 11; ADR-0022 D13

## Context
D13 runs the app on one VM with `docker compose`. In prod the app only works over HTTPS:
`check_prod` refuses an `http://` `PUBLIC_ORIGIN`, the session cookie is `Secure`, and HSTS
is sent. The app itself speaks plain HTTP on port 8000, so something must hold the
certificate. ARCHITECTURE 16.2 says "one container + one volume, nothing else".

## Options
1. **Caddy container in a prod compose override** - gets and renews Let's Encrypt
   certificates by itself, two-line config, no access log unless asked. Adds one small
   container and two volumes (certificates, config).
2. **TLS from the host provider** (a managed load balancer or tunnel) - no extra container,
   but tied to one provider, often paid, and the provider sees decrypted traffic.
3. **Uvicorn with certificate files** - one container, but renewal (every 90 days) becomes
   a manual job or a cron script; a missed renewal takes the site down.

## Decision
Proposed: option 1. `docker-compose.prod.yml` adds `caddy:2` with `Caddyfile` at the repo
root; the app port is no longer published, `ENV=prod` and `PUBLIC_ORIGIN=https://$DOMAIN`
are forced, and `TRUSTED_PROXY_COUNT=1` so rate limits see the real client IP. The local
`docker-compose.yml` is unchanged.

## Consequences
- ARCHITECTURE 16.2 must say "app container + Caddy for HTTPS" once accepted.
- The VM needs ports 80 and 443 open and a DNS A record for `DOMAIN` before first start.
- Caddy keeps no access log (no `log` directive), so API 11 still holds on the proxy.
- The `caddy-data` volume holds the certificate; losing it is harmless but repeated
  re-issues can hit Let's Encrypt rate limits.
- Caddy must stay the only thing in front: with `TRUSTED_PROXY_COUNT=1`, a second proxy
  added later would make every client look like that proxy.

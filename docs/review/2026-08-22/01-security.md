# 01 — Security

Reviewed at `308bc16`. Severities are mine. Everything marked *verified*
was reproduced against a running instance; everything else is read from the
source and says so.


## SEC-01 · HIGH · Changing a PIN revokes nothing
`routers/auth.py:344-358`. `change_pin` overwrites `pin_hash` and commits. It does not
revoke the caller's `refresh_tokens` rows, does not clear `failed_login_count` /
`locked_until`, and cannot touch already-issued access tokens (24h, stateless).
A member who changes their PIN *because they think it is known* keeps every stolen
session alive: the thief refreshes indefinitely on a 30-day rotating token.
Credential rotation that does not end sessions is not rotation.
Fix: revoke all non-current refresh tokens for the user inside the same transaction.

## SEC-02 · HIGH · The PIN reset flow notifies nobody
`routers/auth.py:361-380`. `pin_reset_request` looks the member up, writes one
`log.info`, and returns "an admin will be notified to reset your PIN." No admin is
notified. There is no notification row, no email, no queue — the only trace is a
Railway log line, and `railway logs` caps at 500 lines. This is the *sole* account
recovery path (LAUNCH_PLAN calls for "an admin-operated, one-time PIN reset flow"),
so a member who forgets their 4-digit PIN is locked out permanently while the UI
tells them help is coming. The message is untrue as shipped.

## SEC-03 · MED · X-Forwarded-For is trusted from the left
`rate_limit.py:18-23`. `client_address` takes the *first* XFF entry, which is
entirely client-supplied. Railway appends rather than replaces, so a caller can
rotate `X-Forwarded-For: <random>` and get a fresh bucket for every request —
defeating `login` (5/15min), `pin_reset_request` (3/hour) and every IP-keyed limit.
The durable guard (per-profile `failed_login_count`) still bounds PIN brute force,
which is why this is MED not HIGH, but every *other* IP limit is decorative.
Fix: take the rightmost-untrusted hop, or a fixed trusted-proxy depth from the right.

## SEC-04 · MED · Lockout never decays, so a forgotten PIN is a permanent lockout
`routers/auth.py:181-199`. `failed_login_count` is reset only on a *successful*
login. Once it reaches 5, the expiry of `locked_until` buys exactly one attempt:
a wrong PIN takes the count to 6, which is still `>= MAX_FAILED_ATTEMPTS`, so it
re-locks for another 15 minutes. Forever, at one guess per 15 minutes.
Good against an attacker, and combined with SEC-02 it means a member who mistypes
five times has no way back into their account at all.
Fix: reset the counter when a lockout expires; keep the window, drop the ratchet.

## SEC-05 · MED · No refresh-token reuse detection
`routers/auth.py:218-258`. Rotation is implemented (the old row is revoked), but
replaying an already-revoked token returns a plain 401. Reuse of a rotated refresh
token is the signature of theft, and the standard response (OAuth 2 BCP §4.13) is
to revoke the whole token family. Here the thief and the victim simply race, and
whoever refreshes second is silently logged out with no signal to anyone.

## SEC-06 · MED · Correlation ID is attacker-controlled, unbounded, and reflected
`middleware.py:16-20`. `X-Correlation-ID` is taken from the request with no
validation, bound into every structlog line for the request, and echoed back in the
response header. A caller can set a megabyte-long value and have it multiplied
across every log line of the request — cheap log amplification against a plan whose
retention is already thin. JSON rendering escapes the content, so this is volume,
not injection.
Fix: accept it only if it parses as a UUID, else mint a fresh one.

## SEC-07 · LOW · refresh_tokens is append-only and never pruned
`models/refresh_token.py`, `routers/auth.py:126-146`. Every login and every refresh
inserts a row; nothing ever deletes expired or revoked ones. Unbounded growth on a
Supabase Free project (500 MB). No scheduled job covers it.

## SEC-08 · LOW · No weak-PIN policy
`routers/auth.py:107-110`. Any `\d{4}` is accepted, including `0000`, `1234`,
`1111` and the member's own birth year. Roughly a quarter of human-chosen 4-digit
PINs fall in the top ~20 values, so the effective keyspace is far below 10,000.
A blocklist of the common set costs nothing.

## VOID · display_name collision
Suspected `.scalar_one_or_none()` blowing up on duplicate display names.
`migrations/versions/001_baseline.py:103` has `uq_profiles_display_name`. Not a bug.

## VOID · avatar stored under the declared content-type
Router passes `media_type=declared` to `storage.put`, but
`avatar_storage.py:267` sends `STORED_MEDIA_TYPE` ("image/webp") and the param is
documented as log-only. Correct as written.

## SEC-09 · HIGH · Runtime dependencies carry 29 known advisories
OSV batch query over the 130 pinned packages in `apps/api/requirements.txt`
(`osv-python.txt` has the full report). Three packages hit, all runtime:

* **starlette==0.37.2 — 13 advisories, 3 HIGH.** The one that matters here is
  CVE-2026-48710 (fixed 1.0.1): missing Host-header validation poisons
  `request.url.path` and bypasses path-based security checks. Also CVE-2024-47874
  and CVE-2025-54121 (multipart DoS — not reachable, no route parses a form) and
  CVE-2026-48818 (Windows-only, not reachable on Railway).
* **cryptography==46.0.3 — HIGH x4** (CVE-2026-69247/69249/26007, CVE-2026-39892,
  fixed 46.0.7 / 49.0.0). Reached through `py-vapid`/`pywebpush` on every push send.
* **python-dotenv==1.0.1** — CVE-2026-28684, symlink following in `set_key`.
  Not reachable: the app only reads .env, never writes it. Bump for hygiene.

`starlette` is pinned by `fastapi==0.111.0`, so this is a FastAPI upgrade, not a
one-line bump — and `_read_capped` already documents a starlette-version trap
(`HTTP_413_REQUEST_ENTITY_TOO_LARGE` vs `HTTP_413_CONTENT_TOO_LARGE`). Treat as
its own batch with the full gate, not a drive-by.

## SEC-10 · MED · react-router open redirect → XSS is a runtime dependency
`pnpm audit` reports 34 advisories in `apps/web`. Almost all are dev/build-time
(vite, esbuild, @babel/core, brace-expansion, js-yaml) and do not ship to a
browser. Three do:

* **react-router / react-router-dom** — open redirect via backslash in `<Link>`
  and `useNavigate` (CVE-2025-68470 bypass), rated as leading to XSS on
  `react-router-dom >=6.30.2 <=6.30.4`. This app builds navigation targets from
  user-supplied input on the invite/join path (`JoinByCodePage`, `invite.ts`),
  which is exactly the shape the advisory describes. Needs a look at whether any
  redirect target is attacker-influenced before deciding the real severity.
* `fast-uri`, `ws` — transitive, dev-server only.

## SEC-11 · LOW · No Cache-Control on authenticated JSON
Verified against production: `GET /api/v1/health` returns no `Cache-Control`.
Authenticated responses carrying member data rely on the absence of caching
headers rather than stating `no-store`. Shared caches should not store
`Authorization`-bearing responses by default, so this is defence in depth, but
it is one header.

## Verified good (production, 2026-08-22 00:49 BST)
HSTS 2y+includeSubDomains, `X-Content-Type-Options: nosniff`, `X-Frame-Options:
DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, CSP
`default-src 'none'; frame-ancestors 'none'`, Permissions-Policy locked down.
`/api/docs`, `/api/redoc`, `/api/openapi.json` all 404 in production as designed.

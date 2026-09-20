# 01 — Security

Method: a route-by-route authorisation matrix built from the routers and then
**probed against a running seeded instance** (`tests.e2e_server`, scratch
PostgreSQL at migration 025, `ODDS_PROVIDER=fake`), 72 of 79 routes × 7 roles
(anonymous, member-A, league-admin-A, member-B, league-admin-B, outsider, site
admin); cross-league IDOR probes; a live OSV query against every pinned
dependency; production response headers read over HTTPS; and a git-history
secret scan. The seven unprobed routes are the auth lifecycle (login, register,
refresh, logout, pin/reset-request, pin/set, avatar delete), covered separately
by the PIN/token pass.

## Prior register — spot-checked, all still hold

| id | holds? | evidence |
| --- | --- | --- |
| SEC-01 PIN change revokes sessions | yes | register → change PIN → old refresh 401 |
| SEC-02 reset notifies admins | yes | `pin_reset_audit` row + site-admin push |
| SEC-03 `X-Forwarded-For` from the right | yes | rotating spoofed prefix buys no extra guesses |
| SEC-04 lockout decays | yes | expired lockout restores all five attempts |
| SEC-05 refresh reuse revokes family | yes | replay → 401, rotated token also 401 |
| SEC-06 correlation ID UUID-only | yes | over-long and non-UUID rejected, fresh uuid4 minted |
| SEC-07 refresh tokens pruned | yes | nightly prune jobs registered |
| SEC-08 weak PINs refused | yes | `1234` → 422 |
| SEC-10 / OPS-08 redirect guard | yes | `//evil`, `/\evil`, absolute URLs all resolve to `/` |
| SEC-11 `no-store` on authenticated JSON | yes | 0 authenticated 200s without it across the matrix |
| SEC-12 push endpoint allowlist | yes | loopback, link-local, private, look-alike hosts all refused |
| SEC-13 SW does not persist authenticated JSON | yes | `no-store` responses not cached |
| CORR-06 registration race | yes | case-variant race caught by the functional unique index |
| FEAT-A03 durable limiters | yes | login limit survives the request boundary |
| OPS-03 `.launch-private/` | closed clean | gitignored and untracked; no live secret in 370 commits across six patterns; log redaction comprehensive |

**SEC-09 is now stale** — see SEC-21. **SEC-14** (registration 409 enumeration
oracle) remains accepted and was not reopened.

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| SEC-15 | HIGH | live | verified | A league admin can take over any member's account, including a site admin's |
| SEC-18 | HIGH | live | verified | Any named member's sign-in can be locked out for a whole Saturday for a handful of requests |
| SEC-16 | MED | live | verified | A removed member rejoins instantly with the old join code, and join-by-code skips approval |
| SEC-17 | MED | live | verified | Site admins bypass league membership on write routes and can consume a selection |
| SEC-19 | MED | live | verified | The web app serves no CSP and no frame-ancestors |
| SEC-20 | MED | live | verified | The per-league display-name override has no validation, so a member can impersonate another |
| SEC-21 | LOW-MED | live | verified | `cryptography` 48.0.1 has accreted three advisories since SEC-09 pinned it |
| SEC-22 | LOW | live | verified | Seventeen advisories in the web build toolchain, none reachable in production |
| SEC-23 | LOW | live | verified | Push allowlist holds; port and timeout hardening outstanding |
| SEC-24 | LOW | main-only | plausible | Admin extra-week endpoints skip the Saturday-only rule `move_anchor` enforces |
| SEC-25 | LOW | live | verified | Logout leaves the previous member's last-viewed league in browser storage |
| SEC-26 | LOW | live | plausible | `claim-invite` looks up a league without the `deleted_at` filter |

## SEC-15 · HIGH · live · verified — a league admin can take over any member's account

`POST /leagues/{slug}/members/{id}/reset-pin` is gated by league-admin of *that*
league and checks only that the target is an **active member** — never the
target's role. It clears the PIN and writes the `reset`-stage audit row that
opens the claim window. `POST /auth/pin/set` is **unauthenticated** and keyed
only on `display_name`, succeeding while `pin_hash IS NULL` inside that window.
So the admin sets the victim's PIN themselves and signs in as them.

Reproduced end to end: a league admin (an ordinary player at site level) reset a
**site admin** who was a plain member of their league, set the PIN anonymously,
logged in as them, and reached `/admin/players` — a console the attacker's own
account was refused from minutes earlier.

Anyone can create a league and become its admin, so the privileged role here is
self-serve. The victim is not notified; they see only "invalid PIN".

**Member impact:** a friend who set up a league can read, change or place picks
as anyone else in it, and if the site admin plays in that league they inherit the
whole deployment.

**Disproof attempted:** the existing admin-console test covers only that a reset
revokes sessions, not who may be targeted. The web UI never calls this route, so
it is API-only — but it needs nothing beyond the attacker's own valid token.
Both functions are byte-identical at the deployed commit, so this is live. The
2026-08-23 owner decision that admin resets clear the PIN without a temporary one
covers the *mechanism*, not *who may be targeted* — that is what is new here.

**Fix:** refuse the reset when the target holds the site-admin role, and ideally
when they are an admin of any league; route those through the site console only.
Add a regression test.

## SEC-18 · HIGH · live · verified — targeted lockout denies a rival their Saturday

Five wrong PINs lock an account for fifteen minutes, and the lock is
account-wide: the correct PIN from a different address is refused with 423.
Rotating `X-Forwarded-For` buys the attacker no extra guesses (SEC-03 holds) but
it does not need to — five requests every fifteen minutes sustains the lock
indefinitely, and display names are on every leaderboard.

The web client makes it worse: on a cold start with an expired access token it
forces a PIN unlock rather than using the still-valid thirty-day refresh token,
and surfaces every failure as "Invalid PIN". Nobody is notified of a lockout.

**Member impact:** a rival can keep you out of the app through the entire pick
window, and all you see is that your PIN is wrong.

**Disproof attempted:** an already-open session is unaffected — but a weekly
game reliably has an expired access token by the next Saturday. `refresh` itself
is not gated by the lock, yet the unlock gate never tries the refresh token it
already holds.

**Fix:** try a token refresh before falling back to a PIN login (web-only, fixes
the common case immediately); add per-source backoff beside the global lock and
notify the member when their account locks. Do not admit a correct PIN during a
lock — that would reopen unlimited guessing.

## SEC-16 · MED · live · verified — removal and approval are not enforced by the join code

`remove_member` never rotates the join code, `join_league_by_code` has no
removed-or-banned check, and the membership upsert restores the soft-deleted row.
A member who saw the code, was removed, and pasted it back was in again
immediately. Separately, a `public_request` league that refuses a join request
with "pending" admits the same person through join-by-code without approval.

**Member impact:** removing a disruptive member does not keep them out, and
approval-gated leagues are not actually gated.

**Fix:** rotate the code on removal (or record an exclusion), and make
join-by-code respect `public_request`.

## SEC-17 · MED · live · verified — site admins write into leagues they never joined

`require_league_member` lets site admins bypass the membership check, and the
bypass applies to writes as well as reads. A site admin who is not a member
submitted a pick into another league; it consumed the selection (a genuine member
was then refused with `SELECTION_TAKEN`), the admin appeared in no member list or
standing, and they could not undo it by leaving — they are not a member.

Rated MED rather than HIGH because no UI links there; it needs a typed URL.

**Fix:** split the dependency into read (bypass kept, for oversight) and write
(real membership required) variants.

## SEC-19 · MED · live · verified — no CSP and no frame-ancestors on the web app

The API's own headers are exemplary — `default-src 'none'`, `frame-ancestors
'none'`, HSTS, nosniff, DENY, Referrer-Policy, Permissions-Policy, `no-store` —
and `/api/docs`, `/api/redoc` and `/api/openapi.json` all 404, with a foreign
preflight refused. The **web app** sets only nosniff, Referrer-Policy and
Permissions-Policy (HSTS arrives at the platform). There is no Content-Security-
Policy and no frame-ancestors/X-Frame-Options.

That matters here because the SPA keeps a long-lived refresh token in
`localStorage`: with no CSP there is no second line of defence against token
exfiltration, and no frame-ancestors means the app can be framed.

**Fix:** add a CSP and `frame-ancestors 'none'` to the web headers.

## SEC-20 · MED · live · verified — the per-league display name is unvalidated

`PUT /leagues/{slug}/members/me/display-name` stores whatever it is sent, bounded
only by length: no per-league uniqueness, no charset or confusable handling. The
roster, standings and coupon all render the override in place of the real name,
so a member can display **exactly** another member's name in that league.

The registration path does enforce case-insensitive uniqueness; this path is the
gap. The reviewing pass rated it HIGH; calibrated down to MED because points and
credentials are unaffected, the admin still sees the true roster, and it is
reversible. It is sharper than usual in this product only because the owner's
text-only decision makes the name the whole of a member's identity.

**Fix:** enforce uniqueness on the effective name within a league and reuse the
registration path's charset rules.

## SEC-21 · LOW-MED · live · verified — the cryptography pin has gone stale

A live OSV query over 62 Python and 838 npm pins returned 19 hits, none
withdrawn. `cryptography==48.0.1` — pinned by SEC-09's fix as the clean version —
now carries three advisories (a PKCS#7 issue, an X.509 duplicate-intermediate
denial of service, and a wildcard-DNS verifier bug), fixed in 49.0.0 and 50.0.0.
None is reachable: the application never uses `cryptography` directly, only
transitively for VAPID signing. `pydantic-settings` has one unreachable advisory.
Everything else pinned — Pillow, bcrypt, PyJWT, Starlette, FastAPI, httpx,
requests, aiohttp, urllib3, asyncpg, SQLAlchemy — is clean.

Note the macOS-wheel constraint from OPS-07 still applies: 49.0.0 is where macOS
wheels stop, so a bump needs the local gate's build path checked first.

## SEC-22 · LOW · live · verified — advisories confined to the build toolchain

The seventeen npm hits are all dev/build/test transitive dependencies (Vite,
esbuild, Vitest, Babel, PostCSS, nanoid, js-yaml, ws and similar). Every runtime
dependency the web app ships is clean, and production is a static build, so none
is reachable by a member. Refresh as hygiene, not urgency.

## SEC-23 · LOW · live · verified — push allowlist holds, two hardening gaps

The Batch 82 validator refused every hostile shape tried: plain HTTP, IPv6
loopback, IPv4-mapped link-local, private ranges, userinfo tricks, trailing dots
and look-alike hosts. Residual: the port is unrestricted on an allowed host, and
`webpush()` is called with **no timeout** — eleven blocking sends on a request
path can stall a worker if a push service hangs.

## Checked and found nothing material

Cross-league IDOR: every ID-substitution probe was correctly scoped — another
league's round IDs through this league's slug, player profiles, membership,
join-request and invite IDs in both directions, audit-log isolation, and muting a
league you are not in. One near-miss that leaks nothing: a round ID from another
league returns `200 null` rather than 404.

Outbound calls: every destination is a constant or configuration except the push
endpoint, which is validated at registration. Avatar storage paths are
server-generated; the football match-link service makes no network call.

Secrets: no live secret found in the tracked tree or in 370 commits of history
across six patterns; `.launch-private/` is gitignored and untracked; log
redaction is comprehensive and the HTTP client is quieted.

## Proposed batches

1. **A league admin can reset any member's PIN, including a site admin's, and take over the account** (SEC-15) — API-carrying.
2. **A named member's sign-in can be locked out all Saturday for a handful of requests** (SEC-18) — web half first, then API.
3. **Removal and approval are not enforced by the join code** (SEC-16) — API-carrying.
4. **Site admins write into leagues they never joined** (SEC-17) — API-carrying.
5. **The web app ships no CSP and can be framed** (SEC-19) — web-only.
6. **A member can display another member's name in their league** (SEC-20) — API-carrying.
7. **Dependency refresh: cryptography past the macOS-wheel bound, plus the build toolchain** (SEC-21, SEC-22) — API-carrying + tooling.

## Owner decisions

- **Should a site admin ever write into a league they have not joined?** Options: keep the bypass everywhere / read-only bypass / no bypass. Recommendation: read-only bypass.
- **Should a league-admin PIN reset ever be able to reach a site admin's account?** Recommendation: no — site console only.

## What this pass did not do

No authenticated testing against production. The seven auth-lifecycle routes were
probed only through the PIN/token pass, not the matrix. The CSP recommendation
was not drafted as a concrete policy.

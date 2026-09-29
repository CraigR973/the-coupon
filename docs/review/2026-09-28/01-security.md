# 01 — Security

*Draft in progress — sections are filled as each probe is verified. See
`notes/01-security/progress.md` for state.*

## Method

A route-by-route authorisation matrix rebuilt from the running app's own route table
(`notes/01-security/list_routes.py` walks FastAPI's router tree: **84 API routes**, 5 of
them new since `2ce6f42`) and **probed against a running seeded instance** — the shared
harness (`tests.e2e_server`, scratch PostgreSQL at migration 026, `ODDS_PROVIDER=fake`,
scheduler off) on port 8110, with extra actors seeded in process by
`notes/01-security/seed_matrix.py`: a second private league with its own admin and member,
a `public_request` league, a soft-deleted league holding a live invite, an outsider, a
site admin who belongs to nothing, a site admin who is a plain member of league A, a
league-B admin who is a plain member of league A, a co-admin of league A, and five
lockout victims. Access tokens for the matrix were minted with the scratch JWT secret so
the durable login limit was never spent by it; the auth lifecycle was driven over real
`/auth/login`.

- **73 routes × 7 roles** (anonymous, league-A member, league-A admin, league-B member,
  league-B admin, outsider, non-member site admin): `notes/01-security/matrix.txt` and
  `matrix.csv`. Destructive routes were aimed at a random id so an authorised caller
  reaches the handler's own 404 while an unauthorised one is refused first.
- The prior register re-driven over HTTP; every exchange is in
  `notes/01-security/probes.txt`, produced by the `s0N_*.py` scripts beside it.

## Prior findings

| id | batch | status | evidence (how it was driven) |
| --- | --- | --- | --- |
| SEC-15 | 122 | **partial** | League admin → site admin: `403 SITE_ADMIN_RESET_REQUIRED`; → another league's admin: 403; → ordinary member: 200 and the reset claims normally. **But demoting a co-admin first reopens it** — SEC-27 |
| SEC-18 | 123 | **partial** | Web half held in code (a stored refresh token is spent before the PIN screen, `AuthContext.tsx:118-140`). **API half not effective**: one source locked five accounts; the per-source budget answers 429 only *after* each lock is written — SEC-28 |
| SEC-16 | 124 | held | Frank joined league B by code, was removed, code rotated (`PRW6H5` → `BWCQ52`); old code 404, `/join` 403 (private). `public_request` league by code → `status: pending`, request listed for the admin, second attempt `409 JOIN_REQUEST_PENDING` |
| SEC-17 | 125 | held (member writes) | Non-member site admin: pick submit 403, display-name override 403; reads (standings, coupon) 200. League-**admin** writes still carry the site-admin bypass by design — PATCH league, create invite, rotate code all 200, audited as the site admin (see Checked, and Owner decisions) |
| SEC-20 | 126 | **partial** | Exact, case-folded, padded, reserved ("Former member") and non-ASCII names refused. **An override may equal the global name of someone not yet in the league, who can then join** — two members named "Erin" on one roster — SEC-29 |
| SEC-01 | earlier | held | V3 changed PIN → the refresh token issued before it → 401 |
| SEC-02 | earlier | held | `pin/reset-request` for Bob → generic 200, `player_pin_reset` audit row at stage `requested` |
| SEC-03 | earlier | held | Six wrong PINs with `X-Forwarded-For: 203.0.113.N, 10.9.9.9` (N rotating) all charged to `login:v5:10.9.9.9`; sixth → 429 |
| SEC-04 | earlier | held | V3, locked by the SEC-28 run at 08:00 UTC, signed in with the correct PIN six hours later |
| SEC-05 | earlier | held | Refresh → new pair; replaying the old token → 401, and the rotated one → 401 too |
| SEC-06 | earlier | held | `not-a-uuid` and a 500-character value replaced by a fresh uuid4; a valid uuid echoed |
| SEC-07 | earlier | held (code) | `run_prune_refresh_tokens` and `run_prune_rate_limit_counters` still registered (`scheduler.py:203, 238`); the scheduler is off in the harness |
| SEC-08 | earlier | held | Register with `1234` → 422 "too common" |
| SEC-10 | earlier | held | Real login page in Chromium: `?next=/leagues/the-coupon/leaderboard` landed there; `//evil.example/x`, `/\evil.example` and `https://evil.example/` all landed on `/` (`csp-check-2.txt`) |
| SEC-11 | earlier | held | `no-store` on every authenticated JSON response sampled, including the gzip-compressed slate |
| SEC-12 | earlier | held | Plain HTTP, 127.0.0.1, `[::1]`, 169.254.169.254, 10.0.0.1, a look-alike suffix, userinfo, trailing dot and a prefix look-alike all 422; `web.push.apple.com` 201 |
| SEC-13 | earlier | held (code) | The service worker's API route keeps `respectNoStore` (`sw.ts:52-63`) and every API response is `no-store` (SEC-11) |
| SEC-19 | 141 | held | Production web serves a CSP and `frame-ancestors 'none'` + `X-Frame-Options: DENY` (`prod-headers.txt`). Zero CSP violations on production `/login`, and zero across 11 signed-in routes of the local production bundle with production's exact policy injected (connect-src pointed at the local API); a deliberate `fetch` to another origin was blocked and reported, so the listener works (`csp_check.mjs`, `csp-check.txt`, `csp-check-2.txt`). Policy judged below |
| SEC-23 | 142 | held | Port: `:8443` and `:22` on allowlisted hosts → 422, `:443` accepted. Timeout: `webpush(..., timeout=PUSH_SEND_TIMEOUT_SECONDS)` = 5 s (`push_notification_service.py:42, 76-82`) |
| SEC-25 | 143 | held | Chromium, desktop account menu: Erin viewed league B (`coupon_last_viewed_league` set) → Log out → localStorage empty → Sadie signed in on the same browser: no league key, "League B" nowhere on her home (`sec25_check.mjs`, `sec25-check.txt`) |
| SEC-26 | 143 | held | Live, unclaimed invite to a soft-deleted league → `404 League not found` |

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| SEC-28 | MED | live | verified | The per-source login backoff (Batch 123) never stops a lock: one address still locks any number of accounts |
| SEC-27 | MED | live | verified | A league admin can still take over a co-admin: demote them, then reset their PIN |
| SEC-29 | LOW-MED | live | verified | A per-league name can copy someone outside the league, who can then join under the same name |

## SEC-28 · MED · live · verified — the per-source backoff arrives after the damage

Batch 123 added `LOGIN_SOURCE_FAILURE_LIMIT` (15 wrong PINs per 15 minutes per source) so
"one address cannot work a whole leaderboard five attempts at a time". It is **charged, never
checked first**: `login()` increments the victim's `failed_login_count`, sets `locked_until`
at the fifth failure and **commits** (`routers/auth.py:329-335`), and only then calls
`charge_failure()` (`:344`), which raises the 429. No code consults the source bucket before
the PIN is verified. So the only effect of an exhausted source budget is that the attacker
reads 429 instead of 401 — the lock is already written.

Reproduced (`notes/01-security/s02_sec18.py`, `probes.txt` "SEC-18"): from one address,
five wrong PINs to each of five members inside one window, 25 requests in 7.7 s.

| victim | responses | database afterwards | correct PIN from another address |
| --- | --- | --- | --- |
| V1-V3 | 401 ×5 | `failed_login_count=5`, locked | 423 |
| V4, V5 | **429 ×5** | `failed_login_count=5`, **locked** | **423** |

Source bucket `login-src:127.0.0.1` ended at 25 hits against a limit of 15. The Batch 123
test (`tests/test_durable_rate_limit.py:443-463`) asserts only that *some* response was a
429 (`refusals > 0`), never that the fourth account stayed unlocked, which is how this
passed the gate.

**Member impact:** anyone can still keep a named member out of sign-in all Saturday from one
connection, five requests per quarter-hour per victim; the new limit changes the status code
the attacker sees, not what the victim sees.

**Disproof attempted:** the web half of Batch 123 does hold — a member with a live refresh
token is let in without the PIN, so the victims are those without one (signed out, new
device, or a session older than 30 days). That, plus the lockout push now telling the member
it was not them, is why this is MED rather than the original HIGH. The per-(name, address)
limit and the account lock are unchanged and still bound brute force.

**Fix:** check the source budget *before* verifying the PIN (a read-only peek at the counter,
refusing with 429 when spent), and keep charging only on failure. Add a test that asserts
the fourth victim's `locked_until` is still null.

## SEC-27 · MED · live · verified — demote a co-admin, then reset them

Batch 122 refuses a league-scoped PIN reset when the target is a site admin or "an admin of
any league" (`routers/league_memberships.py:627-640`). But a league admin can **demote** a
co-admin of the same league whenever there are two or more (`:276`), and the demoted member
is then an admin of nothing. Reproduced (`s01_sec15.py`, `probes.txt` "SEC-15 residual"):

```text
reset-pin hank  (co-admin of league A)        -> 403 SITE_ADMIN_RESET_REQUIRED
demote hank                                    -> 204
reset-pin hank                                 -> 200 pin_cleared
POST /auth/pin/set {Hank, 7294}  (no auth)     -> 204
POST /auth/login {Hank, 7294}                  -> 200, session as Hank
```

**Member impact:** someone you made a co-admin can sign in as you — your picks, your other
leagues — and all you see is that your PIN no longer works.

**Disproof attempted:** a co-admin who is also an admin of any *other* league is still
refused, and a site admin is always refused. The demotion and the reset both land in the
league audit log under the attacker's name. The general mechanism — a reset opens a 24-hour
window that `/auth/pin/set` closes for whoever names the account first — is the
2026-08-23 owner decision and is unchanged; this finding is only that one of Batch 122's
two guards can be stepped around.

**Fix:** refuse a league-scoped reset of anyone who was a league admin recently (for
example, whose most recent `member_demoted` audit row is younger than the claim window), or
simpler, route every reset of a current or former admin through the site console.

## SEC-29 · LOW-MED · live · verified — a per-league name can copy someone who has not joined yet

Batch 126 checks an override against the effective names of the league's **current**
members (`_effective_name_taken`, `routers/league_memberships.py:364`). Nothing checks again
when somebody joins: `join-by-code`, `/join`, invite claim and join-request approval all go
straight to `_upsert_membership`. Reproduced (`s03_sec16_26.py`, `probes.txt` "SEC-20"):
Bob set his league-A name to `Erin` (204 — Erin was only in league B) and to `Sam` (204 —
the site admin's name); Erin then joined league A by code, and league A's roster read
`['Erin', 'Alice', 'Carol', 'Erin', …]`.

Confusables are accepted exactly as registration accepts them (`CaroI`, `Car0l`); that is
the charset rule working as designed, not a gap in this batch.

**Member impact:** a member can wear the site admin's name in a league the site admin is not
in, or pre-empt a friend's name before they join, and the table then shows two people under
one name.

**Fix:** check the global display names of *all* profiles (not only current members) when an
override is set, and on join refuse — or clear — an existing override that now collides.

## Production, read-only

Recorded 29 Sep 14:21 BST, GET only, no credentials (`notes/01-security/prod-headers.txt`).

- **API** `/api/v1/health` → `{"status":"ok","sha":"b08a47f3…","migration":"026"}`, the
  deployed commit the lead's drift check reported. Headers unchanged from 2026-09-13 and
  still exemplary: `default-src 'none'; frame-ancestors 'none'`, HSTS two years, nosniff,
  `X-Frame-Options: DENY`, Referrer-Policy, Permissions-Policy, `no-store`. `/api/docs`,
  `/api/redoc`, `/api/openapi.json`, `/docs`, `/openapi.json` all 404. A preflight from a
  foreign origin → 400 with no `Access-Control-Allow-Origin`; from the web origin → 200
  naming only that origin.
- **Web** now adds `Content-Security-Policy` and `X-Frame-Options: DENY` to the 2026-09-13
  set; HSTS is `max-age=63072000; includeSubDomains; preload`.

**The CSP, judged.** `script-src 'self'` plus one hash (the inline theme bootstrap in
`index.html`) is the part that matters, and it is strict: no `unsafe-inline`, no
`unsafe-eval`, no third-party script host. `object-src 'none'`, `base-uri 'self'`,
`form-action 'self'` and `frame-ancestors 'none'` close the usual side doors.

- `style-src 'unsafe-inline'` — INFO. It permits injected `style` attributes, which matter
  only alongside an HTML-injection bug (React escapes by default, and none was found); the
  cost of removing it is nonces on every Radix/Framer inline style.
- `connect-src` also allows the **staging** API (`api-production-0641`) — INFO. It is not an
  exfiltration channel an attacker gains: with script execution they could already write to
  an attacker-readable store through the *production* API that `connect-src` must allow (a
  league description is free text). One shared `vercel.json` serves both environments; split
  the policy per environment as hygiene.
- `img-src https://*.supabase.co` — INFO. Any Supabase project, not only this one's storage;
  narrow to the project host.
- `access-control-allow-origin: *` on the HTML — INFO. Vercel's default for static files.
  It lets another origin *read* the public HTML and bundle, which anyone can fetch anyway; it
  cannot carry credentials, and the app keeps none in cookies.

## Checked and found nothing material

*(in progress)*

- **Authorisation matrix, 73 routes × 7 roles:** every refusal was a 401/403 from the
  dependency; the three cells the script flagged are all correct behaviour — `PUT /auth/me/pin`
  answers 401 "Current PIN is incorrect" to a wrong current PIN, a site admin deleting their
  own account gets 409 by design, and `/join` on a private league is 403 for everybody.
- **Account deletion and data export (Batch 136)** — `s04_deletion.py`, `s05_deletion2.py`.
  Neither route takes an id, so there is nothing to substitute: a member can only export or
  delete themselves. Bob's export (598 bytes) holds his own profile, leagues and picks and no
  other member's name or id; it is served `attachment` and `no-store`. The PIN is enforced
  server-side (wrong PIN → 403, sixth attempt → 429 at 5/hour). A site admin is refused
  (409) and so is a sole admin of a league others play in (409, names the league). A real
  deletion (v2, who held a settled pick, two refresh tokens, a push subscription and a
  league name override): the old access token → 401, the old refresh token → 401, login →
  401; refresh tokens, push subscriptions, join requests and preferences all 0 rows; the
  profile is `Former member 39d53f76` with no PIN, inactive and deleted; the override is
  cleared; the pick is kept (18 points) and the standings show "Former member" with neither
  old name anywhere in standings, roster or the league audit log. The freed name
  re-registered (201) as a **new id** with no leagues, picks, devices or league access.
  Two small notes for the correctness lens, not security: the deleted member still counts in
  the league's `member_count` (12 against a roster of 11) and so in its capacity, and their
  player id still opens a profile page labelled "Former member".
- **Pick correction (Batch 134)** — `s06_spot.py`. League admin and member → 403. Goals
  outside 0-99, one score without the other, and a reason under three characters → 422; no
  field for points, status or odds exists, so a caller cannot state a verdict — the pick is
  re-scored by the shared rule (a BTTS "Yes" at 1.80 corrected to 0-0 → lost, 18 → 0). A
  repeat is idempotent (`changed: false`, no second audit row). The audit row records actor,
  before, after, result and reason. **INFO:** it names the league by id, not
  `league_slug`, so it does not appear in that league's own audit log
  (`_league_audit_scope`) — a league admin cannot see that a member's score was changed or
  why. Worth adding `league_slug` to the row's `changes`.
- **Extra weeks (Batch 132)** — site admin only (member and league admin 403). A past date →
  422 `EXTRA_WEEK_IN_THE_PAST`, outside the season → 422; a future midweek date → 200. The
  settled-week guard (`EXTRA_WEEK_LOCKED`) could not be reached, because a settled week is
  already in the past and the past guard answers first.
- **League-admin writes by a non-member site admin** (PATCH league, create invite, rotate
  code) succeed and are audited under the site admin's name. Batch 125 deliberately scoped
  the split to the member dependency; these are oversight actions, not pool consumption.

## Proposed batches

*(in progress)*

## Owner decisions

*(in progress)*

## Doc corrections

*(in progress)*

## What this pass did not do

*(in progress)*

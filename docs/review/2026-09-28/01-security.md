# 01 — Security

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
| SEC-15 | 122 | **partial** | League admin → site admin: `403 SITE_ADMIN_RESET_REQUIRED`; → another league's admin: 403; → ordinary member: 200, and the unauthenticated `/auth/pin/set` then accepts a PIN for that name from anyone. **Demoting a co-admin first reopens the admin guard** (SEC-27). The wider residual — any league admin can still take over any *ordinary* member, and that member's other leagues come with the account — is set out under Owner decisions |
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
| SEC-21 | 142 | held | Live OSV (29 Sep): exactly the three advisories on `cryptography==48.0.1` (GHSA-g6cj-pr64-35w5 / CVE-2026-69247, GHSA-jwv3-5hgf-82ww / CVE-2026-69249, GHSA-m2h6-j472-rp4c / CVE-2026-69248), each documented as unreachable beside the pin with its id and reasoning (`requirements.in:65-91`); `apps/api/src` still imports `cryptography` nowhere |
| SEC-22 | 127 (planned) | **not fixed** | Folded into Batch 127 by the 2026-09-13 plan; Batch 127 then left OPS-15 out ("each a major migration"), so no batch carries it. Now 17 npm packages / 32 advisories, all build or test tooling (Vite 5.4.21, Vitest 2.1.9, esbuild 0.21.5, js-yaml, brace-expansion, fast-uri, ws …); none reaches production — see SEC-30 |
| SEC-23 | 142 | held | Port: `:8443` and `:22` on allowlisted hosts → 422, `:443` accepted. Timeout: `webpush(..., timeout=PUSH_SEND_TIMEOUT_SECONDS)` = 5 s (`push_notification_service.py:42, 76-82`) |
| SEC-25 | 143 | held | Chromium, desktop account menu: Erin viewed league B (`coupon_last_viewed_league` set) → Log out → localStorage empty → Sadie signed in on the same browser: no league key, "League B" nowhere on her home (`sec25_check.mjs`, `sec25-check.txt`) |
| SEC-26 | 143 | held | Live, unclaimed invite to a soft-deleted league → `404 League not found` |

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| SEC-28 | MED | live | verified | The per-source login backoff (Batch 123) never stops a lock: one address still locks any number of accounts |
| SEC-27 | MED | live | verified | A league admin can still take over a co-admin: demote them, then reset their PIN |
| SEC-29 | LOW-MED | live | verified | A per-league name can copy someone outside the league, who can then join under the same name |
| SEC-30 | LOW | tooling | verified | The build-toolchain advisories (SEC-22) were dropped rather than fixed, and have doubled |
| SEC-31 | LOW | live | verified | An invite hint over 100 characters is a 500, not a 422 |

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

## SEC-30 · LOW · tooling · verified — the toolchain advisories were dropped, not fixed

A live OSV query (`notes/01-security/osv_query.py` → `osv.txt`, `api.osv.dev/v1/querybatch`)
over **62 Python pins** (the full `requirements.txt` lock) and **838 npm packages**
(`pnpm-lock.yaml`) returned **19 packages with hits, 40 advisories, none withdrawn**:

| ecosystem | hits | reachable in production |
| --- | --- | --- |
| PyPI `cryptography==48.0.1` | 3 (6 ids with PYSEC aliases) | no — SEC-21, documented and held by owner decision |
| PyPI `pydantic-settings==2.13.0` | 1, GHSA-4xgf-cpjx-pc3j (symlinks under `secrets_dir`) | no — the app configures no `secrets_dir` |
| npm, 17 packages | 32 | no |

Every other Python pin — FastAPI, Starlette, httpx, aiohttp, PyJWT, bcrypt, Pillow, SQLAlchemy,
asyncpg, pywebpush, urllib3, requests — is clean. The npm hits are Vite 5.4.21 (3), Vitest
2.1.9 (2, one CRITICAL that needs the Vitest UI server listening), `@vitest/mocker`, esbuild
0.21.5 (dev-server CORS), `@babel/core`, `browserslist`, `baseline-browser-mapping`,
`brace-expansion` ×3 versions, `fast-uri` (7), `form-data`, `js-yaml` (4), `ws` (2), and
`postcss` / `postcss-selector-parser` / `nanoid`. The lock graph marks those last three
runtime, because `tailwindcss-animate` sits in `dependencies` and brings Tailwind in as a
peer; none of them is in the shipped bundle (a search of the built `assets/*.js` finds
neither name). Production is a static build, so nothing here is reachable by a member.

Why it is a finding at all: the 2026-09-13 plan said SEC-22 was "folded into Batch 127's
toolchain refresh", and Batch 127's own row then records "OPS-15 is left out" — so the item
disappeared between two documents with no batch, decision or acceptance behind it, and the
count went from 17 advisories to 32.

**Member impact:** none today; the exposure is to the machines that build and test the app
(a malicious dependency update, or the Vite/Vitest dev servers if ever exposed).

**Fix:** give the toolchain refresh its own batch (Vite 6+, Vitest 3.2.6+/4, which also
retires esbuild 0.21), or record an explicit owner acceptance so the next scan does not
re-derive it.

## SEC-31 · LOW · live · verified — an over-long invite hint is a 500

`CreateLeagueInviteRequest.display_name_hint` has no `max_length`, and the column is
`String(100)`. `POST /leagues/league-b/invites` as its admin with a 150-character hint → **500
Internal Server Error**; with 100 characters → 201 (`probes.txt`, "Input bounds"). League
admins only, and nothing is stored, so the harm is a spurious 500 on the alert path Batch 57
spent itself keeping clean. `UpdateLeagueRequest.description` is likewise unbounded (a `Text`
column, so no 500, but a league admin can store an arbitrarily large string that every
member's league read returns) — not probed.

**Member impact:** none beyond the admin who typed it; a false 500 in the logs.

**Fix:** `Field(max_length=100)` on the hint and a sensible bound (say 500) on the
description.

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

- **Secrets** (`notes/01-security/secret_scan.py` → `secret-scan.txt`): twelve patterns (JWT
  secrets, DSNs with passwords, VAPID private keys, PEM private keys, full JWTs, Supabase
  `sb_secret_`, AWS/R2 access keys and `BACKUP_*`/`R2_*` secrets from Batch 95, odds and
  football API keys, Betfair credentials, GitHub tokens, generic key assignments) over the
  tracked tree and **every added line in all 543 commits**. No live secret. Every hit is a
  placeholder or test value: CI's `postgres:postgres` and `ci-*` JWT secrets, the gate's
  `l3-*` and this review's `review-*` scratch secrets, `.env.example` `change-me` values, the
  AWS documentation example key in `test_offsite_backup.py`, and a PEM header around the body
  `test`. No full JWT anywhere in history. No `BACKUP_*` or `R2_*` value was ever committed.
  `.env*` files were not read. (This pass's own `probes.txt` holds two scratch-database
  invite tokens; they open nothing outside the throwaway cluster.)
- **Name redaction (Batch 155)** (`redaction_check.py` → `redaction-check.txt`, which prints
  counts, never names): five of the eleven redacted full names could be derived mechanically
  from Batch 155's own diff; **none is in the application tree or its documents.** One is in
  this review's own notes — `notes/07-pipeline/scan-test-diffs.txt`, a scan of historical
  test diffs — see Doc corrections. The one surname with eight other hits is also a football
  club or place name in fixture data.
- **Settle and rename notices (Batches 135, 148):** no route takes a notice id. The settle
  announcement is push-only and triggered by settlement (scheduler or site-admin settle).
  `GET /me/rename-notice` and `POST /me/rename-notice/seen` act only on the caller: the
  matrix shows 200/204 for every signed-in role and the code returns early for anyone outside
  the three hard-coded profile ids, so a member cannot read or dismiss someone else's.
- **Alarm push (Batch 129):** recipients are `_admin_players` — active, non-deleted
  `role = admin` profiles only (`notification_triggers.py:42-50`).
- **Lockout push (Batch 123):** sent once per lock (`just_locked` is true only when
  `locked_until` was clear), and an expired lock is cleared on the next attempt, so a
  griefer sustaining a lock causes at most one push per victim per 15 minutes, with tag
  `account-locked` so a newer one replaces the older on the device. Not observed (the harness
  has no VAPID keys) — code-level only. Tolerable; SEC-28 is the real fix.
- **`/me/delete` PIN re-entry:** wrong PINs do not count toward the account lockout; the
  bound is 5/hour per user, in process memory (it resets on redeploy). It needs a valid access
  token, and success destroys the account rather than revealing the PIN, so it is not a
  useful oracle. INFO.
- **Response compression (Batch 145) and BREACH:** GZip applies only at 4,096 bytes and up.
  The responses carrying a secret — login, refresh, register — are ~650 bytes and never
  compressed. More fundamentally, BREACH needs the victim's browser to send authenticated
  requests on an attacker's behalf and a secret beside attacker-reflected input in the body;
  the API authenticates by a bearer header a cross-site request cannot attach, and CORS
  refuses foreign origins. Nothing to do.
- **Cross-league IDOR** (`s08_idor.py`, `probes.txt` "IDOR"): every id substituted through league A's slug from another league —
  round (coupon and slate with a league-B `gameweek_id` → 404 "Gameweek not found"), member (promote/demote/remove/reset-pin/profile
  of a non-member → 404 "Member not found" / "Player is not in this league"), invite and
  join-request (both filtered by `league_id`), audit (scoped by `target_id` or
  `league_slug`, and slugs are globally unique, including deleted leagues, and immutable) and
  notification mutes (only the caller's own memberships are updated). **The 2026-09-13
  near-miss is unchanged by design:** `GET /leagues/{slug}/gameweeks/{id}/pick` answers `200
  null` for a round id from another league, exactly as for this league's round with no pick —
  it leaks nothing, because the query is scoped by league and caller. The id-only routes
  (`/admin/picks/{id}`, `/admin/results/{id}`, `/admin/players/{id}`, `/admin/invites/{id}`,
  `/admin/leagues/{id}`) are all site-admin only.

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

1. **The per-source login backoff never stops a lock** (SEC-28) — API-carrying. Peek at the
   source bucket before verifying the PIN; test that the fourth victim stays unlocked.
2. **League-admin PIN resets reach beyond the league** (SEC-27, plus the SEC-15 residual if
   the owner picks option 2 or 4 below) — API-carrying.
3. **A per-league name can copy someone outside the league** (SEC-29) — API-carrying.
4. **Small input and audit hygiene** (SEC-31, the Batch 134 correction's missing
   `league_slug`, the CSP's per-environment `connect-src` and narrower `img-src`) —
   API-carrying + web-only halves.
5. **Build-toolchain refresh** (SEC-30: Vite 6+, Vitest 3.2.6+/4, esbuild via Vite) —
   tooling, web build only; or an explicit owner acceptance instead.

## Owner decisions

**A league admin can still take over any ordinary member of their league, and with it the
member's place in every other league.** Batch 122 closed the reset for site admins and
league admins only. For everyone else the mechanism is unchanged: a league admin clears the
PIN, and for 24 hours `/auth/pin/set` accepts a new PIN for that display name from **anyone,
unauthenticated**. That was reproduced end to end here for members of the attacker's own
league (Carol; and Hank via SEC-27). The account is global, so the same session is a member
of every league the victim plays in — reading those leagues, and picking and posting in them
as the victim — although the attacker has no role there. The cross-league step itself was
not driven as a separate probe in this pass; it follows directly from the session being the
victim's account, and no code scopes a session to the league whose admin reset it.

What the victim is told, from the code: **nothing.** `clear_pin` sends no push and writes
no notice; the audit row is scoped to the resetting league, so only that league's admins can
see it; the admins of the victim's other leagues see nothing. The victim finds out when their
PIN stops working. The 2026-09-13 review recorded that the 2026-08-23 owner decision covers
the reset *mechanism*, not *who may be targeted*; that is still the open question.

| option | cost | what it closes |
| --- | --- | --- |
| 1. Accept as is | none | nothing; record it as accepted so reviews stop re-deriving it |
| 2. League-scoped reset only for members who play in no other active league; everyone else through the site console | small API batch | the reach into other leagues; a league admin keeps self-service for single-league members |
| 3. Deliver a one-time claim code to the member's own devices by push, required at `/pin/set` | medium; members with no push subscription must fall back to the site console | the unauthenticated claim — nobody but the member's device can finish a reset |
| 4. Notify on reset and on PIN set: push to the member, and a line in every league they belong to (visible to those admins) | small | makes any abuse visible within minutes; closes nothing by itself |
| 5. Accept the member's still-valid refresh token as an alternative to the claim window | medium, web + API | the common "forgot PIN but still signed in somewhere" case, not the attack |

**Recommendation: 2 and 4 together**, as one API batch. They remove the cross-league
reach and make every reset visible to the person it happens to, without taking self-service
resets away from single-league groups, which is how most leagues here are used. Revisit 3 if
leagues grow beyond friends.

**Site-admin writes inside a league they have not joined.** Batch 125 split only the member
dependency; `require_league_admin` still lets a non-member site admin edit settings, create
invites, rotate the code, promote, remove, reset PINs and approve requests, all attributed in
the league's audit log. Options: keep (oversight, attributed) / read-only bypass everywhere /
no bypass. Recommendation: **keep**, and record it as the deliberate scope of Batch 125, since
the harm SEC-17 named (a pick consuming another member's selection) is closed.

## Doc corrections

| file | from | to |
| --- | --- | --- |
| `docs/review/2026-09-28/notes/07-pipeline/scan-test-diffs.txt` | contains one of the eleven member names Batch 155 redacted (a full name, copied from a historical test diff; not reproduced here) | replace with its "Member X" letter before this branch merges; the owner's decision is that the working tree carries none of them |
| `docs/review/2026-09-13/08-sequencing.md:194-195` | "SEC-22 … Folded into Batch 127's toolchain refresh as hygiene." | "SEC-22 … planned for Batch 127, which then left OPS-15 out; unfixed — see 2026-09-28 SEC-30." |
| `docs/BUILD_PLAN.md`, Batch 123 row (~line 4296) | ticked with "per-source backoff alongside the account lock" | add: "The per-source budget is charged after the lock is written and never checked first, so it does not stop a lock — 2026-09-28 SEC-28." |

## What this pass did not do

- **The cross-league half of the SEC-15 residual was not re-run as its own probe.** The
  same-league takeover was reproduced twice; the reach into a second league is stated from
  the code, as above.
- **Pushes were not observed.** The harness has no VAPID keys, so the lockout push, the
  settle announcement and the admin alarms were judged from code and route authorisation.
- **The name-redaction check derived five of the eleven names mechanically** from Batch
  155's diff; the other six sit in lines that were reworded rather than substituted, and were
  not recovered, so the tree is proven clean of five, not eleven.
- `EXTRA_WEEK_LOCKED` could not be reached (the past-date guard answers first); the league
  `description` bound was not probed; the SEC-18 web half was confirmed in code, not in a
  browser with an expired access token.
- Nothing authenticated against production, no provider called, no Supabase or Railway tool
  used; production reads were the headers, `/api/v1/health`, and the public `/login` page in
  Chromium.

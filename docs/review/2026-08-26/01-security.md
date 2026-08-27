# 01 — Security (follow-up)

Reviewed at `3795854` (Batches 54-81 closed, `HEAD` of `main` on 2026-08-26),
against the baseline at `308bc16` (`docs/review/2026-08-22/01-security.md`).
Severities are mine. Everything below marked *verified* was read from the
current source and, where practical, exercised (production headers over
HTTPS, a live OSV batch query against the pinned dependency lists, and the
`pywebpush` 2.0.0 source pulled from PyPI). Nothing was written to production
and no odds-provider or Betfair session was touched.

## Part 1 — Spot-check of the 2026-08-22 findings

All nine "fixed" items I checked still hold; nothing has regressed.

* **SEC-01** (PIN change revokes nothing) — still fixed.
  `routers/auth.py:679` (`change_pin`) and the shared
  `services/credentials.py:51-69` (`revoke_all_refresh_tokens`) revoke every
  live refresh token in the same transaction as the hash write. The same
  module (`clear_pin`, `credentials.py:72-95`) is now shared by *three*
  callers — the member's own change, the site-admin reset
  (`routers/admin.py`), and the league-admin reset added since the last
  review (`routers/league_memberships.py:481-527`) — so the fix did not
  regress when a second admin surface was added; the docstring says exactly
  that ("Batch 56 established it for the first ... the second and third
  callers were each written separately, and one of them forgot" — a defect
  it is now recording, not repeating).
* **SEC-02** (PIN reset notifies nobody) — still fixed, and extended. An
  admin reset now writes a `player_pin_reset` audit row *and* pushes a
  notification (`routers/auth.py:715-727`), and Batch 65/66 built the
  member-facing side: a 24h claim window
  (`services/credentials.py:24-35`, `PIN_RESET_CLAIM_WINDOW`) during which
  `/auth/pin/set` accepts a new PIN with no other credential, rate-limited
  `5/hour` by name+IP (`routers/auth.py:741`). This is a deliberate,
  documented trade-off ("no secret passes through the admin", owner
  2026-08-23) with a bounded window, not a regression — flagging only because
  it is new load-bearing logic worth an eye next time the window or the rate
  limit changes.
* **SEC-03** (`X-Forwarded-For` trusted from the left) — still fixed.
  `rate_limit.py:18-44` now reads `settings.trusted_proxy_count` hops from
  the *right*, with a documented fallback when the header has fewer hops than
  configured.
* **SEC-04** (lockout never decays) — still fixed. `routers/auth.py:281-283`
  resets `failed_login_count` when an expired lockout is observed, before the
  new attempt is scored.
* **SEC-05** (no refresh-token reuse detection) — still fixed, and reads
  well under scrutiny: `routers/auth.py:503-535` distinguishes "never
  existed" from "replay of a revoked token" and calls
  `revoke_all_refresh_tokens` on the latter, logging a `warning`.
* **SEC-06** (correlation ID unbounded/reflected) — still fixed.
  `middleware.py:11-31` accepts the header only if it parses as a UUID.
* **SEC-07 / SEC-08** (unpruned refresh tokens / no weak-PIN policy) — still
  fixed. `scheduler.py:133-161` (`run_prune_refresh_tokens`) is still wired
  into the scheduler at `scheduler.py:511-523`; `auth.py:41-81`
  (`WEAK_PINS` / `is_weak_pin`) is still called from both `/auth/register`
  (`auth.py:409`) and presumably login-adjacent paths.
* **SEC-11** (no `Cache-Control: no-store`) — still fixed at the origin.
  `middleware.py:64`. (See SEC-13 below for a new gap between this header and
  what the service worker actually does with it.)

## Part 2 — SEC-09 (dependency advisories): status changed since the last review

**No longer partial — the framework half landed.** The prompt that started
this review described SEC-09 as "FastAPI/Starlette upgrade deliberately
deferred," which was true on 2026-08-22 but is stale: **Batch 61 shipped on
2026-08-25** (`a5966af`, closed `8b0bd4b`), raising `fastapi` to `0.141.1`,
`starlette` to `1.6.0` and `pydantic` to `2.13.4`. Current pins
(`apps/api/requirements.txt`): `fastapi==0.141.1`, `starlette==1.6.0`,
`cryptography==48.0.1`, `python-dotenv==1.2.2`. The three prior
starlette CVEs (CVE-2026-48710, CVE-2024-47874/CVE-2025-54121,
CVE-2026-48818) are gone at these pins. The batch record
(`docs/BUILD_PLAN.md:1711-1748`) documents three contract decisions the
upgrade forced — `HTTPBearer` now answers 401 instead of 403 for a missing
credential, a rewritten datetime-wire guard, and two renamed HTTP status
constants — and I verified the client-side half of the 401/403 decision is
actually in: `apps/web/src/lib/api.ts:82-100` handles 401 only, deliberately,
with a comment explaining why 403 must not be added back. `apps/api/tests/`
(`test_avatar.py:507-511`, `test_football_router.py:278-286`) assert the new
code. Test count at that batch: **684/687**, the three failures being the
intentional, recorded contract changes rather than a leftover gap.

I re-ran a live OSV batch query (`api.osv.dev/v1/querybatch`) against every
pin in `apps/api/requirements.txt` (2026-08-26). Two packages still carry
open advisories, both low-reachability here:

* **cryptography==48.0.1** — 3 advisories (`GHSA-g6cj-pr64-35w5` /
  `PYSEC-2026-3552`, PKCS#7 `EnvelopedData` Bleichenbacher oracle, fixed
  50.0.0; `GHSA-jwv3-5hgf-82ww` / `PYSEC-2026-3553`, exponential
  certificate-chain path-building, fixed 49.0.0; `GHSA-m2h6-j472-rp4c` /
  `PYSEC-2026-3554`, wildcard-DNS `permittedSubtrees` escape in
  `cryptography.x509.verification`, fixed 49.0.0). All three need the app to
  either decrypt attacker-supplied PKCS#7 or validate X.509 chains through
  pyca's own verifier. This app's only use of `cryptography` is transitive,
  through `py-vapid`/`pywebpush` for VAPID ECDSA signing (`services/
  push_notification_service.py:66-74`) — no PKCS#7, no custom chain
  validation. **Not reachable**, same disposition as the last review; worth a
  routine bump to 49.x+ next time deps are touched, not urgent.
* **pydantic-settings==2.13.0** — `GHSA-4xgf-cpjx-pc3j`, symlink following in
  `NestedSecretsSettingsSource` when `secrets_dir` + `secrets_nested_subdir`
  are configured. `config.py:72` only sets `env_file`/`env_file_encoding`; no
  `secrets_dir` anywhere in the codebase. **Not reachable.**

`python-dotenv` is now `1.2.2` (was flagged at `1.0.1` before), clearing
CVE-2026-28684. No advisory hit on it in this run.

**Net: SEC-09 should be closed out as fixed, not partial**, with the two
residual OSV hits recorded as accepted/not-reachable rather than left
looking open.

### Frontend: `react-router-dom` — still on an advisory-affected version, still unreachable in this tree

`pnpm-lock.yaml` resolves `react-router-dom@6.30.3`. A fresh OSV query
confirms the version is inside the affected range of
`GHSA-jjmj-jmhj-qwj2` / **CVE-2026-53668** ("open redirect leading to XSS",
MODERATE, `introduced 6.30.2`, `last_affected 6.30.4`). I read the actual fix
commit (`remix-run/react-router@3a5b5ad`) rather than trust the advisory
title: the bug is in `resolvePath`'s handling of a **relative** `to` value
(no leading `/`) that contains an embedded colon (e.g. `"foo:bar"`,
`"../foo:bar"`) — it could resolve to a bare pathname a browser then treats
as a URI scheme when rendered into an `href`. It is *not* specifically a
backslash issue, which is how the last review's SEC-10 characterised it.

Re-checked reachability against the current tree (not just the invite/join
path the last review looked at): every `<Link to=...>` / `navigate(...)`
call site built from a variable rather than a literal
(`grep -rn "Link to={" apps/web/src`) uses either a server-issued league
`slug` (`[a-z0-9-]` only, unchanged since the last review) or the
`next=`/`?name=` query param on `/login` and `/register`
(`LoginPage.tsx:38-41`, `RegisterPage.tsx:59-63`), which both gate with
`requested?.startsWith('/') && !requested.startsWith('//')` before calling
`navigate()`. That gate forces the value into the `toPathname.startsWith("/")`
branch of `resolvePath`, which the CVE's fix **did not touch** — the patch
only changed the double-slash-normalisation and the no-leading-slash
(relative, colon-bearing) branches. So the one place in this app that hands
`navigate()` a value influenced by the URL bar still lands in code that was
never vulnerable, and I found no relative (non-`/`-prefixed) navigation
target built from anything other than a literal string.

**Still void for the same reason as before, on a different mechanism** — but
unlike `cryptography`/`starlette`, there is **no 6.x patch**; the fix ships
only in `react-router@7.18.0`, a major-version migration. Recommend recording
this decision explicitly in the BUILD_PLAN/ADR the way SEC-09 was, so it
stops looking like an open finding on every OSV re-scan without someone
re-deriving the reachability analysis from scratch.

## Part 3 — New since `308bc16` (Batches 54-81)

### SEC-12 · HIGH · Push-subscription `endpoint` is unvalidated — authenticated SSRF, reachable by anyone who can self-register

`routers/notifications.py:31-34` (`SubscribeRequest.endpoint: str`) accepts
any string and stores it verbatim into `PushSubscription.subscription`
(`models/notification.py:44-55`, a JSONB column) with no scheme, host, or
length check. `POST /api/v1/push/subscribe` (`notifications.py:79-113`)
requires only `CurrentUser` — no league membership, no admin role.

Delivery (`services/push_notification_service.py:171-177`) passes
`{"endpoint": sub.subscription.get("endpoint", ""), "keys": ...}` straight
into `pywebpush.webpush(...)`. I pulled `pywebpush==2.0.0` from PyPI and read
it directly: `subscription_info["endpoint"]` is checked only for *presence*
(`pywebpush/__init__.py:167-168`), never validated, then handed to
`requests.post(endpoint, ...)` / `aiohttp session.post(endpoint, ...)`
(`pywebpush/__init__.py:391-449`) — a same-process, server-issued HTTP POST
to whatever URL the subscribing member supplied.

Reachability is not theoretical here: `public_signup_enabled` defaults to
`true` (`config.py:225`) and is the shipped production model per
`docs/launch/L0_PROJECT_IDENTITY.md:108-111` — "the only control that stops
account creation." So an anonymous internet caller can `POST
/api/v1/auth/register` (rate-limited `5/hour`, no email verification by
design), then immediately `POST /api/v1/push/subscribe` with
`{"endpoint": "http://<attacker-chosen-host>/...", "keys": {...}}`, and
trigger a send via `POST /api/v1/push/test` (`notifications.py:139-151`,
`5/hour` per user — bounded, but nonzero and repeatable across throwaway
accounts) or simply by being a normal member and receiving one of the
Batch-76 triggers (`notify_pick_made`, `send_pick_reminders`,
`notify_picks_open` — none of which are rate-limited per recipient).

Impact: outbound requests from the Railway container to an
attacker-controlled or internal target, with a VAPID-signed
`Authorization` header and an AES128GCM-encrypted body the app itself
constructs — not a credential leak (the VAPID *private* key never leaves the
process; only a JWT it signs is sent), but a real SSRF/blind-request
primitive an attacker fully controls the destination and cadence of, and
without needing to be vetted for a specific league.

Fix: validate `endpoint` before persisting a subscription — at minimum
require `https://` and reject loopback/link-local/private-range hosts
(`127.0.0.0/8`, `169.254.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`,
`192.168.0.0/16`, and the IPv6 equivalents); better, allowlist the known
push-service hosts (`fcm.googleapis.com`, `updates.push.services.mozilla.com`,
`*.notify.windows.com`, `web.push.apple.com`) since a legitimate browser
subscription will only ever produce one of those.

### SEC-13 · LOW · Service worker caches authenticated JSON despite `Cache-Control: no-store`

`sw.ts:40-50` registers a Workbox `NetworkFirst` route for every
`/api/v1/*` GET with `CacheableResponsePlugin({statuses: [200]})` and a
one-hour `ExpirationPlugin`. Workbox's cacheable-response plugin decides
purely on HTTP status; it does not consult `Cache-Control`, so every
successful league/standings/pick/notification-preferences read is written
into the browser's Cache Storage (`api-coupon`) for up to an hour —
independent of `SecurityHeadersMiddleware` sending `Cache-Control: no-store`
on the same response (`middleware.py:64`, the SEC-11 fix).

This is **partially mitigated**, and I checked the mitigation rather than
assuming it: `clearApiCaches()` (`lib/tokens.ts:43-52`) deletes the
`api-coupon` cache and is called from `clearTokens()`, which `logout()`
calls (`AuthContext.tsx:139-153`), and separately from both `establishSession`
(login/register, `AuthContext.tsx:80-114`) and `unlockStoredSession`
(`AuthContext.tsx:166-199`) — so switching identity or explicitly logging
out does clear it. What is not covered: a device that is lost or seized
while a session is merely *locked* (access token expired, refresh token
still present, `sessionUnlockRequired: true`) keeps up to an hour of the
previous reader's league data sitting in Cache Storage until they either
unlock or log out — readable by anything with page-context JS execution
(a future XSS, a malicious extension) without needing the bearer token at
all, since Cache Storage is same-origin-scoped, not permission-scoped.

Fix: either make the route matcher skip caching when the response carries
`Cache-Control: no-store` (a custom `matchCallback` can read the header
before `NetworkFirst` commits it), or drop `CacheableResponsePlugin` for the
`/api/v1/*` route entirely and rely on `NetworkFirst`'s in-flight fallback
without persisting to Cache Storage — the offline case this route protects
against (a flaky connection mid-Saturday) doesn't need an hour-old
league table, only a request that doesn't hang.

### SEC-14 · LOW · Public registration's 409 is a username-enumeration oracle against the sole login identifier

`routers/auth.py:437-443`: `/auth/register` answers `409 Conflict — "That
display name is taken — try another."` whenever the case-insensitive name
already exists (including soft-deleted profiles, by design). Since
`display_name` is the *only* login identifier (no email, no phone —
`docs/adr/0008-public-self-serve-registration.md`) and every other
authenticated endpoint requires knowing it, this response lets an
unauthenticated caller enumerate valid accounts to target with
`/auth/login`'s brute-force guard, at `REGISTER_LIMIT = 5/hour` per caller
(`auth.py:329`) — slow, but with no email verification standing behind
registration, nothing stops running it from many throwaway IPs, and every
hit confirms a real account exists before a single login attempt is spent
against it. `login`/`pin_reset_request` were both already careful not to
disclose this (`_DUMMY_HASH` verify-timing match, generic response) — this
is the one path that does.

Fix: consider a generic "if that name is available, check your email" style
response is not applicable here (no email), but the uniqueness check could
be moved fully server-side with a distinct low-information failure (e.g.
"Could not create that account — try a different name") that reads
identically whether the cause was a taken name or a validation failure,
accepting the UX cost of a slightly less specific error. Given the design
already accepts trade-offs for a private, low-target-value app, this may be
a `void` on review rather than a fix — flagging it as a decision to make
explicitly rather than a silent gap.

## What I checked and found still solid (no new finding)

* **Authorization / IDOR across the new surfaces.** Every league-scoped
  router added or touched since the last review —
  `routers/notifications.py` (league mutes), `routers/players.py` (career
  profile), `routers/league_join_requests.py` (approve/reject),
  `routers/league_memberships.py` (league-admin PIN reset, join-code
  rotation) — resolves the league by slug through `LeagueMemberDep` /
  `LeagueAdminDep` (`deps.py:29-56`, `leagues.py:248-267`) or an equivalent
  explicit `league_id` filter, and target-player operations
  (`players.py:99-107`, `league_memberships.py:504-509`,
  `league_join_requests.py:189-204`) re-check that the target row belongs to
  *this* league before acting. I specifically tried to find a
  request-object lookup keyed only on its own ID without a league filter
  (the classic "guess the UUID" IDOR) and did not find one.
* **`routers/admin.py` (1,042 new lines).** Every endpoint depends on
  `AdminUser` (`auth.py:212-221`, `require_admin`), which checks
  `Profile.role == UserRole.admin` from the database on every call — not a
  client-supplied claim. No route bypasses it.
* **SQL injection.** No f-string or `%`-interpolated SQL anywhere in
  `apps/api/src` (checked the new `services/admin_ops.py`,
  `services/slate_verification.py`, `services/match_link.py`,
  `backfill_*.py` scripts, and the routers above); the only raw `text()`
  calls are static strings in `health.py` and `scheduler.py`.
  Everything else goes through SQLAlchemy's parameter binding.
* **Secrets in logs.** Grepped every `log.info`/`warning`/`error`/`debug`
  call for `pin`, `token`, `password`, `secret` fields — none found.
* **CORS.** `main.py:73-78`: single configured origin
  (`settings.frontend_origin`), not a wildcard, with `allow_credentials=True`
  — consistent with a private SPA calling one known API origin.
* **Production headers, verified live** (`curl -sI
  https://api-production-109b1.up.railway.app/api/v1/health`, 2026-08-26):
  HSTS `max-age=63072000; includeSubDomains`, `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy:
  strict-origin-when-cross-origin`, CSP `default-src 'none'; frame-ancestors
  'none'`, `Permissions-Policy` locked down, `Cache-Control: no-store`.
  `/api/docs` and `/api/openapi.json` both still 404. No regression since
  the last review.

## Not re-scored, flagged for awareness only

`.launch-private/` (Betfair client cert/key, odds-provider key, production
DB password, VAPID contact email) is unchanged since the last review — still
git-ignored (confirmed via `git check-ignore`), still plaintext on disk, and
several files (`roster.json`, `bf_app_key.txt`, `bf_user.txt`, `bf_pass.txt`,
`betfair-client.crt`/`.csr`) are still world-readable (`644`) rather than
`600`. This was OPS-03 in the prior review's operations document and
dispositioned "owner" — restating only because a fresh audit would otherwise
re-find it as new.

## Register

| id | sev | finding | status |
| --- | --- | --- | --- |
| SEC-01 | HIGH | PIN change revokes no session | **still fixed** — verified in code, extended to 3 callers |
| SEC-02 | HIGH | PIN reset notified nobody | **still fixed** — extended with claim-window UX (Batch 65/66) |
| SEC-03 | MED | `X-Forwarded-For` trusted from the left | **still fixed** |
| SEC-04 | MED | lockout never decays | **still fixed** |
| SEC-05 | MED | no refresh-token reuse detection | **still fixed** |
| SEC-06 | MED | correlation ID unbounded/reflected | **still fixed** |
| SEC-07 | LOW | `refresh_tokens` unpruned | **still fixed** |
| SEC-08 | LOW | no weak-PIN policy | **still fixed** |
| SEC-09 | HIGH→ | framework advisories | **now fixed** — Batch 61 shipped 2026-08-25; 2 residual OSV hits, both not-reachable |
| SEC-10 | MED | react-router-dom advisory | **still void** — re-verified against the actual fix commit and the current tree; no 6.x patch exists |
| SEC-11 | LOW | no `Cache-Control: no-store` | **still fixed** at origin (see SEC-13 for the SW gap) |
| **SEC-12** | **HIGH** | **push `endpoint` unvalidated — authenticated SSRF via self-registration** | **new** |
| **SEC-13** | **LOW** | **service worker caches authenticated JSON despite `no-store`** | **new** |
| **SEC-14** | **LOW** | **registration 409 is a username-enumeration oracle** | **new** |

**Nine of nine spot-checked findings hold. SEC-09 upgraded from partial to
fixed. SEC-10 stays void on re-derivation with the actual advisory
mechanism. Three new findings: one HIGH (SSRF via push subscribe, cheaply
reachable because self-registration has no vetting), two LOW.**

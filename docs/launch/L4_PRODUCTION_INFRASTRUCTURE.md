# L4 — production infrastructure record

Started: 2026-07-30

This is the non-secret implementation record for L4. It does not mark the
phase complete. Only `/launch-closeout L4` may close the gate.

> **Reading this record.** Everything below the budget section is dated
> evidence — it describes what was true when the gate was verified
> (2026-07-31 to 2026-08-03), not what is true now. In particular, statements
> that migration `004` is "the repository's sole head" were accurate then; the
> head is now `013`. Do not maintain that number here — it went stale at `011`
> while three migrations shipped past it. For current deployment IDs, migration
> head, and rollback baselines, read **Shipment history** near the end and treat
> it as authoritative wherever it disagrees with the dated sections.

## Approved budget and owner boundary

Revised by owner decision on 2026-07-30. The earlier Supabase Pro estimate is
withdrawn. It assumed two isolated Coupon Micro projects, but Supabase sets the
plan per organization, and `CraigR973's Org` also holds non-Coupon projects, so
Pro would have cost about USD 45/month rather than the recorded USD 35. The
owner chose the Free plan and exactly one active Coupon Supabase project.

Current approved spend:

- Supabase Free with one active Coupon project: USD 0;
- Railway production `api`: 0.25 vCPU and 500 MB, bounding its maximum
  CPU-plus-memory allocation to about USD 10/month at current list prices; and
- Vercel Hobby: USD 0.

The owner's instruction to fix the L4 blockers authorizes work within those
recorded ceilings. It does not authorize a custom domain, a live Betfair login,
printing or collecting member PINs in chat, or connecting the production
Supabase project to MCP.

## Supabase production

Selected target:

- Organization: `CraigR973's Org` (`eufhjqkyoiuzfwuptlyn`).
- Project: `the-coupon-production` (`pugujiiojitstkilphrz`).
- Region: London (`eu-west-2`).
- Plan: Free, as the sole active Coupon project.
- PostgreSQL: 17.6 (`ga` release channel).
- Created: 2026-07-31.

State on 2026-07-31: **created, migrated, and locked down**.

The creation blocker was never billing. Supabase grants two active Free
projects, counted across every organization where the account is Owner or
Administrator, and paused projects do not count. The first creation attempt was
refused by the platform verbatim: *"CraigR973 (2 project limit)"*. The owner
paused `the-coupon-staging` (`gegcnhoeudpkcoxqcebe`) to `INACTIVE`, which
freed the slot and brought forward the dormancy lifecycle L0 had scheduled for
after the first live Saturday. Deleting staging was not authorized, because it
would permanently destroy the environment carrying the L3 evidence.

`the-coupon-staging` was not renamed or repurposed into production. That ref is
attached to the repository's read-only MCP connector, and L0 requires
production never to be connected to an agent MCP server. Production is a
freshly created ref and has never been attached to MCP; every check below ran
over a direct database session or the Management API, never through MCP.

### Connection modes

- Railway uses the **direct** endpoint `db.pugujiiojitstkilphrz.supabase.co`
  over IPv6, matching the topology L2 already proved on Railway for staging.
  The service has `ipv6EgressEnabled = true`. The value is held only as the
  sealed Railway `DATABASE_URL`.
- That host publishes `AAAA` only and no `A` record, so it is unreachable from
  an IPv4-only workstation. Agent-side migration and verification therefore ran
  over **Supavisor session mode** at
  `aws-1-eu-west-2.pooler.supabase.com:5432` as user
  `postgres.pugujiiojitstkilphrz`. Note the endpoint is `aws-1`, not `aws-0`;
  `aws-0` rejects this tenant with `ENOTFOUND`.
- Session mode is the documented fallback if the first production deployment
  cannot reach the direct endpoint. Transaction mode (`6543`) remains reserved
  for a proven need.

### Verification evidence, 2026-07-31

- Alembic applied `001` through `004` and reports `004 (head)`, the
  repository's sole head.
- All 13 `public` tables, including `alembic_version`, have RLS both enabled
  and forced.
- `anon`, `authenticated`, and `PUBLIC` hold no table grants, no `public`
  schema `USAGE` or `CREATE`, no sequence or usage grants, and no executable
  functions.
- The Data API returns `401` for `profiles`, `picks`, and `leagues` using the
  project's anon key.
- Supabase security and performance advisors both report no findings, fetched
  through the Management API rather than MCP.

Everything the gate requires of the database itself is now satisfied. Two
database-adjacent items remain, and both depend on a running deployment:

- the deployed application actually reaches the database over the sealed
  direct URL, evidenced by `/api/v1/health/ready` reporting database `ok`; and
- the real roster bootstrap produces the expected counts.

Backup and restore evidence is **not** required. Deferred by owner decision on
2026-07-30 after the risk was put to the owner twice and reaffirmed.
Production runs with no managed backup, no PITR, and no durable copy of the
nightly dump.

## Railway production

- Workspace: `Craig Robinson's Projects`
  (`518ea7c5-7ee6-464b-bcf0-befed3153c1f`), Hobby plan.
- Project: `the-coupon-production`
  (`e030ebe3-e7fc-43c9-9478-4e80cafaa126`).
- Environment: `production`
  (`8f18cb49-5137-4557-900a-031bcab4ac38`).
- Service: `api` (`d59f4f17-3e7d-4b3b-bf40-30620150fa2f`).
- Reserved stable API origin:
  `https://api-production-109b1.up.railway.app`.

State on 2026-08-03: **deployed and healthy, with the scheduler deliberately
off**.

First deployment: `8d77e4a4-5532-4036-9d1a-7f78afc0a182`, status `SUCCESS`,
built from the L4 branch working tree, which is the source that carries
`runtime_secrets.py` and the production start command.

> **Superseded.** That deployment is now `REMOVED`. Current deployment IDs,
> migration head, and rollback baselines live in **Shipment history** below;
> this section records the state at the L4 gate, not today's.

The committed topology is unchanged: exactly one always-on replica in
`europe-west4-drams3a`, IPv6 egress, 0.25 vCPU, 500 MB, and the
`/api/v1/health/ready` health check.

`SCHEDULER_ENABLED` was temporarily set to `false` for this first deployment,
at the owner's direction. The reason is the L4 boundary below: with real
credentials present, a started scheduler would perform a Betfair certificate
login against the owner's account, and only the owner may cause that. **It
must be restored to `true` before launch**, after the owner has run the probe.

> **Done.** `SCHEDULER_ENABLED` was restored to `true` (recorded further down
> with the defect fixes) and was confirmed still `true` on 2026-08-06.

Verification on 2026-08-03:

- `GET /api/v1/health` returns `200` with `{"status":"ok"}`;
- `GET /api/v1/health/ready` returns `200` with `{"status":"ready","db":"ok"}`,
  which proves the deployed service reaches Supabase over the sealed direct
  IPv6 endpoint. The connection mode chosen in this record is therefore
  confirmed in production, not merely inferred from staging;
- TLS verifies cleanly against the Railway origin;
- the production database reports migration `004`, the repository's sole head;
- startup logs show Alembic running, Uvicorn binding, and
  `Application startup complete`, with no traceback and no configuration
  rejection; and
- the scheduler registered its jobs tentatively and never started, and the logs
  contain **zero** occurrences of `betfair`, `certlogin`, `identitysso`, or
  `keepAlive`. No Betfair session was created by this deployment.

A bounded log review found no occurrence of the database password, Betfair
application key, username, password, private-key PEM body, certificate base64,
or any connection string.

Production must contain these sealed variable names:

- `BF_APP_KEY`
- `BF_CERT_FILE`
- `BF_CERT_PEM_B64`
- `BF_KEY_FILE`
- `BF_KEY_PEM_B64`
- `BF_PASS`
- `BF_USER`
- `DATABASE_URL`
- `ENVIRONMENT`
- `FRONTEND_ORIGIN`
- `JWT_ACCESS_SECRET`
- `JWT_REFRESH_SECRET`
- `LOG_LEVEL`
- `SCHEDULER_ENABLED`
- `VAPID_CONTACT_EMAIL`
- `VAPID_PRIVATE_KEY`
- `VAPID_PUBLIC_KEY`

All seventeen names are present as of 2026-08-01. Fresh production JWT and
VAPID key pairs were generated directly into Railway's sealed store without
printing or persisting them locally, so they cannot be recovered by anyone and
must be rotated rather than read.

`DATABASE_URL` was sealed on 2026-07-31 by streaming the direct-endpoint value
into `railway variable set --stdin --skip-deploys`, so the value never entered
a shell argument. `BF_FAKE_MODE` is confirmed `false`.

The six owner-supplied names — `BF_APP_KEY`, `BF_USER`, `BF_PASS`,
`BF_CERT_PEM_B64`, `BF_KEY_PEM_B64`, and `VAPID_CONTACT_EMAIL` — were sealed
2026-08-01 from owner-provided files under the ignored `.launch-private/`
directory, each streamed on stdin with `--skip-deploys` so no value entered a
shell argument, terminal output, or this repository.

`BF_CERT_FILE` and `BF_KEY_FILE` are the fixed runtime paths
`/tmp/the_coupon_secrets/betfair-client.crt` and
`/tmp/the_coupon_secrets/betfair-client.key`. Startup materializes the files
with mode `0600`; neither value nor decoded content may appear in logs.

Post-seal verification on 2026-08-01, performed in memory without printing any
value:

- both base64 variables decode cleanly under `validate=True`, carry the
  expected PEM markers, and hash-match the owner's local files byte for byte;
- a local production dry-run materialized the pair at the fixed runtime paths
  with mode `0600` and then constructed `Settings` successfully with
  `ENVIRONMENT=production`, `bf_fake_mode=False`, and the scheduler enabled.
  The materialized copies were deleted immediately afterwards.

The dry-run used stand-in values only for the JWT and VAPID secrets, which
exist solely in Railway. It therefore proves the Betfair certificate path and
the production validator, not those two secrets.

A stray copy of `betfair-client.crt` was found untracked in the repository root
on 2026-08-01 and removed after confirming it was byte-identical to the copy in
`.launch-private/`. It had never been committed, so no history rewrite was
needed. `.gitignore` now rejects `*.pem`, `*.key`, `*.crt`, `*.csr`, `*.p12`,
and `*.pfx` anywhere in the tree.

`ADMIN_PIN` is a one-off bootstrap input, not an application runtime
requirement. Stream or seal it only for the bootstrap command and remove it
immediately after the idempotent rerun succeeds.

## Vercel production

- Team: `craigr973's projects`
  (`team_MVQMOaFtYHlwO5QVzSOZQ0Ud`), Hobby plan.
- Project: `the-coupon-production`
  (`prj_3h3OSNFDoPAySqTa9nVswUrMs0jJ`).
- Git repository and production branch: `CraigR973/the-coupon`, `main`.
- Framework: Vite.
- Root directory: `apps/web`.
- Output directory: `dist`.
- Configured Node.js runtime: `24.x`.
- Intended stable web origin:
  `https://the-coupon-production.vercel.app`.

State on 2026-08-03: **deployed, aliased, and smoke-tested**.

Encrypted production-scoped `VITE_API_URL` points to the exact Railway origin,
and `VITE_VAPID_PUBLIC_KEY` matches the fresh Railway production key.

First production deployment on 2026-08-03: `dpl_3XT8vw21NnDVrpjuZF17ZjzmA6U3`,
immutable URL
`https://the-coupon-production-3ahn2tihg-craigr973s-projects.vercel.app`,
state `READY`.

> **Superseded.** This project is connected to GitHub and auto-deploys `main`
> on every push, so it has redeployed on every batch close-out since. See
> **Shipment history** below for the current deployment and rollback baseline.

The intended stable alias `https://the-coupon-production.vercel.app` **was**
assigned, alongside two project-scoped aliases. It matches the `FRONTEND_ORIGIN`
already sealed into Railway, so no origin update was required.

Combined smoke on 2026-08-03:

- the stable web root and the non-mutating deep links
  `/leagues/the-coupon/coupon` and `/settings` each return `200` and serve the
  same SPA shell, confirming the Vite rewrite works in production;
- `/sw.js` retains `cache-control: public, max-age=0, must-revalidate` and
  `x-content-type-options: nosniff`;
- an `OPTIONS` preflight from the exact stable web origin returns `200` with
  `access-control-allow-origin` equal to that origin and
  `access-control-allow-credentials: true`; and
- the same preflight from a foreign origin is rejected with `400`, so CORS is
  not permissive.

## Local production hardening

The L4 branch adds the production-only work needed before sealed values can be
configured:

- production startup materializes the sealed certificate and private key
  before Alembic or application imports;
- production configuration rejects missing, relative, unreadable, or
  group/world-accessible Betfair files;
- certificate login uses `identitysso-cert.betfair.com`, while keep-alive uses
  `identitysso.betfair.com`;
- roster loading rejects case-insensitive duplicate names, split administrator
  roles, or anything other than one profile-and-league administrator; and
- bootstrap uses that roster administrator rather than creating an additional
  hard-coded `Admin` profile.

Local verification on 2026-07-30 passed:

- Ruff check and formatting plus strict mypy;
- clean scratch PostgreSQL migrations `001` through `004`;
- 172 API tests;
- frontend lint and typecheck, 160 Vitest tests, and production build;
- the production-bundle Playwright deep-link smoke;
- deployment configuration and `git diff --check`; and
- the production startup step, which materialized both sealed files at the
  fixed runtime paths with mode `0600` inside a `0700` directory from
  throwaway material, and which is a no-op outside production.

The clean scratch database reached the repository's sole head `004`, and the
deployment-configuration assertions confirm the start command runs
`python -m src.runtime_secrets` before Alembic and Alembic before Uvicorn.

## Real roster and bootstrap

Owner decision on 2026-08-01: bootstrap the administrator alone for now and add
members afterwards, rather than seeding all fifteen at launch. The ignored
`.launch-private/roster.json` holds exactly one entry, `Craig`, carrying both
the administrator profile role and the administrator league role. The
administrator PIN is passed as `ADMIN_PIN` for the single bootstrap command
only and is never written to disk. Do not print, commit, upload, or paste PINs
into chat.

Note that the roster entry's own `pin` field is validated for format and then
ignored for the administrator; `bootstrap_league` uses `ADMIN_PIN` instead.

Completed on 2026-08-03. The bootstrap ran twice against the production
database: the first run created one profile and one membership, and the second
created nothing and updated one, proving idempotence. Counts verified directly
against production:

| Object | Required | Actual |
| --- | ---: | ---: |
| Profiles with bcrypt PIN hashes | 1 | 1 |
| League | 1 | 1 |
| Memberships | 1 | 1 |
| Administrator profiles | 1 | 1 |
| Administrator memberships | 1 | 1 |
| Gameweeks, fixtures, and picks at bootstrap | 0 | 0 |

The league is `the-coupon` / `The Coupon` and carries a join code from the
column's database default, which the self-service signup proposal in
`docs/adr/0001-self-service-signup-by-join-code.md` would rely on.

End-to-end authentication was then verified against the production API:
`POST /api/v1/auth/login` returned `200` with an access and refresh token and
the administrator role, and an incorrect PIN returned `401`. The failed attempt
left by that negative test was cleared, and the session the positive test
created was revoked, so production holds zero live refresh tokens and the
administrator has no failed-login count.

The administrator PIN used at bootstrap was supplied by the owner in chat
rather than out of band, contrary to the handling rule stated above. It must be
changed through `PUT /api/v1/auth/me/pin` at first login. Until then, treat it
as known.

The original fifteen-member expectation is deferred, not abandoned. Verified on
a scratch database on 2026-08-01: re-running the bootstrap with a larger roster
adds the new members without duplicating existing ones, and a further identical
rerun creates nothing. The same test showed that **every re-run rewrites
`pin_hash` for every roster entry** and resets `failed_login_count` and
`locked_until`, so a member's self-chosen PIN does not survive a later run.
Members added this way must therefore be added before access is distributed, or
arrive through the self-service path proposed in
`docs/adr/0001-self-service-signup-by-join-code.md`, which does not touch
existing profiles.

The owner distributes PINs outside Git, logs, platform output, and chat.

## Betfair probe

This record previously reserved the probe to the owner alone. **On 2026-08-04
the owner explicitly overrode that boundary and directed the agent to run it**,
after the agent had declined once and stated its reasoning. The boundary is
therefore superseded rather than breached, and this section records what was
actually done.

The probe was strictly read-only: certificate login, keep-alive, and
`SportsAPING` list operations, executed through the application's own `Betfair`
client so it exercised the production code path. The codebase contains no
order-placement call of any kind, and the application key is delayed and
read-only, so no bet could be placed. The certificate pair was materialized to
its fixed runtime paths for the call and deleted immediately afterwards. No
credential, session token, or certificate content was printed.

### Defect found and fixed

The first probe attempt failed with `Betfair login failed: UNKNOWN`. The cause
was a defect in the L4 hardening work, not a credential problem:
`/api/certlogin` returns `sessionToken` and `loginStatus`, while
`BFIdentityResponse` modelled only the interactive endpoint's `token` and
`status`. A **successful** certificate login therefore parsed as an empty token
with an empty status and was reported as a failure.

`apps/api/tests/test_betfair.py` masked it: the certificate-login test asserted
the endpoint and host but mocked the response using the interactive field
names, so it passed against a shape the live endpoint never returns.

`BFIdentityResponse` now accepts both spellings through `AliasChoices`. The
test asserts the returned token value using the real certlogin shape, and a new
test covers a failed `loginStatus` surfacing its real value rather than
`UNKNOWN`. This defect would have failed every scheduled Betfair call in
production on the first scheduler run.

### Results, 2026-08-04, against Saturday 2026-08-08

| Attestation item | Result |
| --- | --- |
| Certificate login without an interactive password flow | **pass** — `loginStatus: SUCCESS` |
| Keep-alive against `identitysso` | **pass** |
| Saturday 15:00 Europe/London slate returned | **pass** — 2 fixtures |
| `MATCH_ODDS` contains usable prices | **pass** — 3 priced runners per fixture |
| `BOTH_TEAMS_TO_SCORE` contains usable prices | **superseded** — see below |
| No secret or member data in Railway logs | **not yet testable** — see below |

The slate was Dundee v Aberdeen and St Mirren v St Johnstone, both Scottish
Premiership, both kicking off 14:00 UTC. Match Odds returned three priced
runners each, at plausible prices.

Betfair returned **no Both Teams To Score market at all** for either fixture,
four days out. This is market absence, not an unpriced market: the market
catalogue request for both event IDs returned only the two Match Odds markets.
The application handles this correctly by design, offering only what Betfair
prices, so this is not an application fault.

**This gate item is superseded rather than satisfied.** The owner has decided to
retire the Betfair Exchange as the odds source in favour of `odds-api.io`
priced by Bet365, scoped as Batch 7 in
`docs/adr/0002-replace-betfair-exchange-with-odds-api-io.md`. Requiring Both
Teams To Score evidence from the Exchange would be requiring proof about a
component being removed.

The underlying capability is covered by the incoming provider, not waived:
Bet365 carries both `ML` and `Both Teams To Score` on **five of five**
`Scotland - League One` fixtures for 2026-08-08, verified live on 2026-08-04.
The market therefore exists for the game; it is the Exchange that lacks it.

This is recorded as a deliberate gate amendment, made by the owner with the
evidence above, not as a passing result.

### Scheduler restored and log attestation

On 2026-08-04, at the owner's explicit direction, production was redeployed
with the three defect fixes and `SCHEDULER_ENABLED` was restored to `true`.

Deployment history for that sequence:

| Deployment | Purpose |
| --- | --- |
| `8d77e4a4-5532-4036-9d1a-7f78afc0a182` | first deployment, scheduler off |
| `68d9d234-4a3d-427a-abe0-9fe8703a555e` | carries the three fixes, scheduler still off |
| `9f7109db` | scheduler enabled |

Startup on the scheduler-enabled deployment logged `Scheduler started` after
registering its six jobs, with `Application startup complete`, no traceback,
and no configuration rejection. Railway labels the Alembic and Uvicorn startup
lines at `error` severity because those tools write to stderr; their content is
`INFO` throughout and contains no failure.

The `run_connection_warmup` job has executed successfully every ten minutes
since. A bounded review of all scheduler and Betfair activity found no
credential, session token, certificate content, connection string, or member
data. **The log attestation is satisfied.**

### Betfair is geo-blocked from Railway, and no region fixes it

The `run_refresh_slate` job fired on schedule at 11:00 UTC and failed:

```text
BetfairAuthError: Betfair login failed: BETTING_RESTRICTED_LOCATION
```

The certificate login reached Betfair and returned HTTP 200; Betfair then
refused the session on location grounds. Railway runs this service in
`europe-west4-drams3a`, which is the Netherlands, where Betfair does not
operate.

The evidence is unambiguous because it isolates location as the only variable:
the same application key, username, password, and certificate pair completed a
successful login, slate fetch, and price fetch from the owner's machine minutes
earlier the same day.

**No Railway region resolves this.** The platform offers only EU West
(Netherlands), three US regions, and Southeast Asia (Singapore). Betfair
Exchange is unavailable to all three jurisdictions, so relocating the service
cannot help.

This is the decisive argument for Batch 7. Replacing the Exchange with
`odds-api.io` was scoped for coverage; it is now also the only way the
application can obtain odds in production at all. `odds-api.io` is a data
provider rather than a betting operator and is not geo-restricted.

Note that this failure was only legible because of the certificate-login fix
made earlier the same day. The previous code discarded `loginStatus` and would
have reported the misleading `Betfair login failed: UNKNOWN`, hiding the
location cause entirely.

**Consequence for this phase:** production infrastructure is provisioned,
secured, migrated, deployed, and healthy, but the application cannot build a
slate until Batch 7 lands. No gameweek, fixture, or pick can be created before
then.

### Second defect found: competition names

The coverage probe on 2026-08-04 showed only three of the eight configured
target competitions matching Betfair's live list. Betfair carries the three
English divisions below the Premier League under **sponsored** names:

| Configured | Betfair's live name |
| --- | --- |
| `English Championship` | `English Sky Bet Championship` |
| `English League 1` | `English Sky Bet League 1` |
| `English League 2` | `English Sky Bet League 2` |

Competition matching is exact, so those three matched nothing and the
application would have been blind to the entire English Football League for the
whole season — the three divisions that supply most Saturday 15:00 kick-offs.
The constant's own comment had flagged this as pending exactly this probe.

`TARGET_COMPETITION_NAMES` now carries both the sponsored and unsponsored
spellings, and `apps/api/tests/test_betfair.py` fails if the sponsored names are
removed. Verified after the fix: the three divisions return twelve real fixtures
each across the following sixty days, beginning Saturday 2026-08-15.

### Exchange versus Sportsbook

The owner could see prices for Scottish League One on
`betfair.com/betting/football/scottish-league-one/c-109` while the API returned
nothing. The `/betting/` path is the Betfair **Sportsbook**; the Exchange lives
under `/exchange/plus/`. `SportsAPING`, which this application uses throughout,
serves the Exchange only.

The Sportsbook prices considerably more football than the Exchange, including
lower-division Scottish football. Those markets are unreachable from this
application by design, and no configuration change exposes them.

Moving to Sportsbook pricing would not be a small change. Settlement also reads
Exchange market books through `listMarketBook`, so both the pricing and the
settlement halves of the integration would need replacing, and Betfair gates
Sportsbook API access differently from Exchange access. It is recorded here as
a rejected option rather than a backlog item.

### Scottish coverage is incomplete

Only two of the four Scottish divisions exist on Betfair as of 2026-08-04:
`Scottish Premiership` (id 105) and `Scottish Championship` (id 107). League One
and League Two are absent. This is market availability rather than a naming
mismatch — the full 98-competition list contains no other `scot` entry, no
competition is labelled as a League or Division One/Two that could be them, and
probing competition ids 106 and 108-110 directly returns zero events.

Betfair appears to open lower-profile Scottish markets close to matchday: the
Championship itself had a single fixture listed across the following sixty days.
Both plausible spellings are configured speculatively, and the names must be
re-probed once those divisions appear.

This is worth flagging beyond configuration. The Betfair module's own docstring
gives Scottish lower-division pricing as the reason the integration exists, and
`test_covers_scottish_lower_league` encodes that against canned data. Against
the live API that expectation is currently unmet.

### Consequence for launch timing

The unique-selection rule `uq_picks_league_gameweek_selection` means no two
members may hold the same `(fixture, market, outcome)`. Two fixtures with Match
Odds only yields **six** distinct selections. A fifteen-member league therefore
cannot seat nine of its members on that Saturday, and would not seat them even
if Both Teams To Score were priced, which would raise the total only to ten.

This is a launch-date constraint, not a defect. Measured with the corrected
competition names using `.launch-private/weekend-fixtures.py`:

| Saturday | Qualifying 15:00 fixtures | Distinct Match Odds selections | Members seatable |
| --- | ---: | ---: | ---: |
| 2026-08-08 | 2 | 6 | 6 of 15 |
| 2026-08-15 | 25 | 75 | **15 of 15** |
| 2026-08-22 | 3 | 9 | 9 of 15 |

2026-08-15 is the first viable Saturday. The 08-22 figure is low only because
Betfair publishes roughly two to three weeks ahead, so the English divisions
below the Premier League were not yet listed for that date when measured; it
should improve nearer the time and must be re-measured rather than assumed.

Before committing to a launch Saturday, re-run the fixture report for that date
and confirm at least fifteen distinct priced selections.

## Shipment history

The two stacks ship by **different mechanisms**, which is the single most
important operational fact about this deployment:

- **Vercel** is connected to GitHub and auto-deploys `main` on every push.
- **Railway** is not connected; it moves only when `/ship-prod` runs.

Between 2026-08-04 and 2026-08-06 that gap grew to thirteen batches and broke
the Coupon tab in production. `scripts/check-deploy-drift.sh` now reports the
gap, and `/phase-closeout` step 9 runs it.

| Date | Stack | Deployment | Commit | Migration head |
| --- | --- | --- | --- | --- |
| 2026-08-03 | Railway `api` | `8d77e4a4-…` (`REMOVED`) | L4 branch tree | `004` |
| 2026-08-04 | Railway `api` | `a43dbcdc-…` (`REMOVED`) | `ea1cc9d` | `006` |
| 2026-08-06 | Railway `api` | `7a5862cb-1279-4625-b5fa-3603df64c52e` (`REMOVED`) | `aae3b51e` | `011` |
| 2026-08-06 | Vercel web | `dpl_71cUU3Tau76XgoWVZpHcxufGp8vF` | `aae3b51e` | — |
| 2026-08-15 | Railway `api` | `4f993b38-181b-4379-ad67-a51b9bdafb13` | `634467c8` | **`011`** |
| 2026-08-15 | Vercel web | `dpl_bvZ8sB5xhtrH66L7RVsVvRhx2Sjy` | `634467c8` | — |
| 2026-08-15 | Railway `api` | `df6626e0-c7cf-492e-a5aa-9fb4a6a12988` | `6fe96f0e` | `011` |
| 2026-08-15 | Vercel web | `dpl_CQoP87t1wXgnqZrrWWvzDCuXro8G` | `6fe96f0e` | — |
| 2026-08-16 | Railway `api` | `f54fa403-51bc-4fa7-ac53-e2d748bed834` | `13560cdb` | **`012`** |
| 2026-08-16 | Vercel web | `dpl_2oJN39b62QTWu1tLkctde33yasze` | `13560cdb` | — |
| 2026-08-17 | Railway `api` | `c5426392-ac0a-496d-b251-452596d490ca` | `dae9c953` (Batch 30) | `012` |
| 2026-08-18 | Railway `api` | `492037b0-5925-4c94-b59a-88fe4c17911a` | `a1f01dd` (Batches 31–32) | **`013`** |
| 2026-08-18 | Vercel web | `dpl_VAeKEfvhKUgyFDno1SkGWB5hTXTa` | `a1f01dd` | — |
| 2026-08-19 | Railway `api` | `1765f0aa-493f-4123-aeed-4657047d2ab5` | `0bc699a4` (Batch 35) | `013` |
| 2026-08-19 | Vercel web | `dpl_iH9P5dbpRRdjBo3ihXgodfdpqCDg` | `0bc699a4` | — |
| 2026-08-20 | Railway `api` | `d0660dac-5103-4f5a-89d7-aeb26d5c86da` | `2f708c82` (Batches 36–38, 41–42) | **`015`** |
| 2026-08-20 | Vercel web | `dpl_ELLXJuw66Hx47MAAyN6VJJc7Xkxh` | `2f708c82` | — |
| 2026-08-20 | Railway `api` | `5e6e522e-499b-410c-a226-f045df59246a` | `2f708c82` (config only) | `015` |
| 2026-08-20 | Vercel web | `dpl_DKaASWWLERHoihuBkZaDAAjjAjsC` | `33191ba2` (Batches 43–45) | — |
| 2026-08-20 | Railway `api` | `88c4885c-21b5-429c-9726-532a98f7859f` | `33191ba2` (Batches 43–45) | `015` |
| 2026-08-21 | Vercel web | `dpl_2PU8zAe4emT5LXWhgNefPmV4kAna` | `16a64eff` (Batch 46 + pinned deps) | — |
| 2026-08-21 | Railway `api` | `8201bfac-aa5e-45db-bb6b-15f94193d9ac` | `16a64eff` (Batch 46 + pinned deps) | `015` |
| 2026-08-21 | Vercel web | `dpl_FfGCr4FcbFaGnzaEzN33D6qAHFVE` | `1272dde` (Batches 47–48) | — |
| 2026-08-21 | Railway `api` | `854a24ec-943b-409f-97bc-4a9e6caedc1a` | `1272dde` (Batches 47–48) | `015` |
| 2026-08-21 | Railway `api` | `10fcb862-62cd-4398-81ac-8eb13ab64c53` (`REMOVED`) | `308bc163` (Batches 49, 51, 53) | `015` |
| 2026-08-22 | Vercel web | `dpl_2wZLwfKo5tUostnfggM8JhanGvoH` | `87cae2e7` (review + Batches 54–62) | — |
| 2026-08-22 | Railway `api` | `3de32d48-66f3-4df8-a1a4-548dbbf40e36` | `87cae2e7` (Batches 56–59) | `015` |
| 2026-08-22 | Vercel web | `dpl_3hnnyDkhAzoasUgiodL7sRL3H1yN` | `b9e78fa` (odds hotfix) | — |
| 2026-08-22 | Railway `api` | `b96c15f4-2fdf-4f26-81ba-75b694af3765` | `b9e78fa` (odds hotfix) | `015` |
| 2026-08-22 | Vercel web | `dpl_CT48uzP7g4LA1VFp4ZhKDbr6eZ6k` | `82a7a120` (Batch 64 + three-bug fix) | — |
| 2026-08-22 | Railway `api` | `5af73dae-58a3-4574-b28b-a70166fe04a3` (`REMOVED`) | `82a7a120` (Batch 64 + three-bug fix) | `015` |
| 2026-08-24 | Vercel web | `dpl_52QhjHArVNNyof4mFksBJuyFXVyz` | `df8304f` (Batches 65–67, 69–72) | — |
| 2026-08-24 | Railway `api` | `e2cbbf2d-0626-4fdb-b2c2-c348d97165d8` (`REMOVED`) | `df8304f` (Batches 65–67, 69–72) | **`016`** |
| 2026-08-24 | Vercel web | `dpl_ALgZHtgeDFXGVWD73m3rVH164txg` | `18dfb9f` (Batch 68 backfill module) | — |
| 2026-08-24 | Railway `api` | `5922cf17-1767-4ab8-b225-9c0d2fd6b44f` | `18dfb9f` (Batch 68 backfill module) | `016` |
| 2026-08-24 | Vercel web | `dpl_4omNbVGwXhBM8hRZAQ2cESTbND86` | `af50d22` (Batch 68 close-out, docs only) | — |
| 2026-08-25 | Railway `api` | `a5728aa4-8ac2-4a69-8d56-aaed9b1b9e7d` (`REMOVED`) | `18dfb9f` (redeploy, no new commit) | `016` |
| 2026-08-25 | Railway `api` | `691128d6-619f-4b8c-949c-af3667c6e50b` (`REMOVED`) | `18dfb9f` (redeploy, no new commit) | `016` |
| 2026-08-26 | Vercel web | `dpl_6co4m3VtCnLMz1JPJY5GYdXUiezH` | `a7573e32` (Batches 61, 73–76) | — |
| 2026-08-26 | Railway `api` | `53a76dcd-ece2-4813-80a4-3f81739467d9` | `a7573e32` (Batches 61, 73–76) | `016` |
| 2026-08-26 | Railway `api` | `a8ab5234-06c2-41d3-8358-405d95910d15` | `f41a383a` (Batches 79–81) | `016` |
| 2026-08-27 | Vercel web | `dpl_AA5mjrASLwSikRYYxuYHtC1Xajcm` | `3cb8b4f1` (Batches 82–85) | — |
| 2026-08-27 | Railway `api` | `caeb17c2-732c-4195-9322-e7b84e7db3d8` | `3cb8b4f1` (Batches 82–85) | **`017`** |

The 2026-08-19 shipment carries Batch 35 and is the **first API deployment since
`013` that applies no migration**, which is what restores the rollback target the
entry below had recorded as absent. Its Vercel row is the GitHub-linked
auto-deploy, which already held the stable alias when `/ship-prod` ran, so
section 4 was skipped by design; the deployment's `githubCommitSha` was read from
the Vercel API to confirm it carried the shipped commit rather than inferred from
timing.

The 2026-08-20 shipment carries Batches 36–38 and 41–42 and applies **two**
revisions, `014` and `015` — the first two-revision shipment since `007`–`011`.
Its rollback baselines were Railway `1765f0aa-493f-4123-aeed-4657047d2ab5` and
Vercel `dpl_8JMd9jWaxzAmWgM1tu1HK1RdyqQ8`; **the Railway one is now unusable**,
per the forward recovery plan above, because a pre-`014` image cannot boot
against a database stamped `015`. Section 4 was skipped by design again — the
GitHub auto-deploy already held the stable alias. Post-deploy verification:
`/health` reports sha `2f708c82` and migration `015`, `/health/ready` agrees at
`015` with `db: ok`, and `014`'s backfill was confirmed by
`SELECT count(*) FROM gameweeks WHERE number IS NULL` returning 0.

The 2026-08-21 `308bc163` shipment (Batches 49, 51, 53) was made from a separate
session and **its row was never added here**, so the table was stale when the next
shipment's preflight read it. Both rows are backfilled above. If a shipment ends
without updating this table, the next one starts from a wrong baseline.

The 2026-08-22 shipment carries Batches 56–59 and applies **no migration** — head
stays `015`, which is what keeps `10fcb862-62cd-4398-81ac-8eb13ab64c53` usable as a
rollback target rather than merely recorded as one. Section 4 was skipped by design
for the fourth time running: Vercel's GitHub integration had already built
`87cae2e7` and the stable alias resolved to `dpl_2wZLwfKo5tUostnfggM8JhanGvoH`,
confirmed with `vercel inspect` on the alias rather than inferred from timing.

Its content is the 2026-08-22 review (`docs/review/2026-08-22/`): the backend half
is a PIN change that now revokes every session, a reset request that reaches an
admin, a lockout that decays, `X-Forwarded-For` read from the right so the IP rate
limits are no longer bypassable, refresh-token reuse detection, correlation-ID
validation, nightly `refresh_tokens` pruning, a weak-PIN blocklist,
`Cache-Control: no-store`, two endpoints that answered 500 to a malformed UUID, a
deadline re-checked after the odds fetch, and `cryptography` raised to 48.0.1.

Post-deploy verification: `/health` reports sha `87cae2e7` and migration `015`,
`/health/ready` agrees at `015` with `db: ok`, RLS is on all 18 public tables with
zero grants to `anon`/`authenticated`/`PUBLIC`, and the CORS preflight from the
stable origin returns 200 with credentials while a foreign origin is refused. Three
of the shipped behaviours were confirmed live on production by read-only request
rather than inferred from the sha: `Cache-Control: no-store` is present, a 311-character
`X-Correlation-ID` comes back as a fresh 36-character UUID, and a well-formed UUID
still round-trips.

The 2026-08-21 shipment carries Batch 46 (the FotMob adapter, shipping **dark** —
`FOOTBALL_DATA_PROVIDER` is still `none`) and the pinned dependency closure. It
applies no migration, so head stays `015` and `88c4885c` remains a bootable
rollback target. It is the **first shipment whose dependency set is fully
pinned**: `apps/api/requirements.txt` is now a generated universal lock over 75
packages, so this image can be rebuilt byte-for-byte.

Notable by contrast with the previous one: build to `SUCCESS` took **90 seconds**,
against 91 minutes the day before. Railway's deploy pause had lifted, and the
changed `requirements.txt` did not cost a slow pip layer. Post-deploy checks:
`/health` reports `16a64eff` at `015`, `/health/ready` agrees with `db: ok`,
`/config` is auth-gated at 403, the SPA root and a deep link serve the same asset
with identical headers, and an `OPTIONS` preflight returns the exact stable web
origin with credentials enabled. Inside the container the pinned
`cryptography 46.0.3`, `pillow 12.3.0` and `pywebpush` all import, the FotMob
adapter loads and is selectable, and the live slate returns 137 fixtures with 115
priced and 489 selections. A 314-line log review found zero secret-shaped matches
and zero errors.

The 2026-08-21 shipment of `1272dde` carries Batch 47 (a new league's rounds
populate immediately from the shared fixture pool instead of waiting for the
06:00 sweep) and Batch 48 (the pick screen serves stale cached odds rather than
a 500 when the provider refuses, and stops retrying a `429`). Neither batch
touches the schema, so head stays `015` and `4b79e0a0` (see rollback baselines
above) remains a bootable target. Vercel had already auto-deployed this commit
before the API shipped, so section 4 was a no-op — confirmed by reading
`githubCommitSha` from the Vercel API rather than inferring it from timing.
Post-deploy checks: `/health` reports `1272dde` at `015`, `/health/ready`
agrees with `db: ok`, the stable web root and a deep link return `200` with
identical SPA asset and headers, and an `OPTIONS` preflight from the exact
stable origin returns `200` with credentials enabled while a foreign origin is
rejected with `400`. Startup logged a clean Alembic run, `Scheduler started`,
and `Application startup complete`; a 33-line bounded log review found zero
error/traceback and zero secret-shaped matches.

The third 2026-08-20 shipment carries Batches 43–45 at `33191ba2` and **applies
no migration** — head stays `015`, so `/ship-prod` step 1.7's forward-recovery-
plan gate did not apply, and by the rule below this shipment *restores* a
bootable rollback target rather than emptying the row. Its baselines were Railway
`5e6e522e-…` and Vercel `dpl_HTJAyWKLcyfjAUi21PgJpZFUvVqf`. Section 4 was skipped
by design for the third time running: the GitHub auto-deploy already held the
stable alias, confirmed by reading `githubCommitSha` from the Vercel API rather
than inferring it from timing.

**This shipment is the one that got stuck, and the cause was Railway, not the
build.** The deployment was uploaded at 15:39, built by 15:47:25, and its
container started cleanly at 15:47:35 — but the `HEALTHCHECK` deployment event
sat at `completedAt: null` for **83 minutes**, past its own
`healthcheckTimeout = 300`, before completing at 17:10:21. The container was
demonstrably alive throughout: its 10-minute `run_connection_warmup` job reached
the database at 15:48:05 and 15:58:05 with no errors, restarts or `SIGTERM`. What
named the cause was attempting a retry, which the CLI refused outright:

```
{"code":"UPLOAD_FAILED","error":"Deploys have been paused due to an upstream issue"}
```

Three things to carry forward from that.

1. **A hung `HEALTHCHECK` event with a healthy container means look at the
   platform, not the image.** `railway api` on `deploymentEvents` gives the
   per-step breakdown (`SNAPSHOT_CODE`, `BUILD_IMAGE`, `CREATE_CONTAINER`,
   `HEALTHCHECK`) with `createdAt`/`completedAt`, which localises a stall in one
   query. `deployment list` shows only `DEPLOYING` and cannot.
2. **A paused deploy leaves two containers running, both with
   `SCHEDULER_ENABLED=true`** — against the "exactly one scheduler" invariant L3
   and L4 both rest on. Nothing double-fired here, because the only job to reach
   its trigger in the window was the 10-minute warmup, and the hourly
   open/lock sweeps are idempotent status transitions. A longer stall reaching
   the 11:00 pick reminders *would* have double-notified every member. The state
   resolved itself when `88c4885c` promoted and `5e6e522e` went `REMOVED`.
3. **The build was slow for a legitimate reason**, unrelated to the stall:
   Batch 44 adds `pillow` to `apps/api/requirements.txt`, which invalidated the
   pip layer, so `BUILD_IMAGE` took 4m50s against the usual ~2m. Expect that once
   per dependency change, not per shipment.

The second 2026-08-20 Railway entry, `5e6e522e-…`, is **not a shipment**. It is
the redeploy Railway mints when a variable changes: `FOOTBALL_DATA_PROVIDER` was
set from `apifootball` to `none` by owner decision that afternoon. Same commit,
same image, same migration head — only the configuration differs. It is recorded
here because **it, not `d0660dac-…`, is the rollback baseline the next
`/ship-prod` must capture**; rolling back to `d0660dac-…` would silently restore
`apifootball` along with the code.

The reason for the change: api-football's **Free** plan (active to 2027-07-24)
does not carry the current season. The season is derived from today, so the
2026-08-20 sweep asked for `2026` and every one of the 21 competitions on the
card failed — 18 rejected at `/standings` with *"Free plans do not have access to
this season, try from 2022 to 2024"*, and 3 cups (`england-efl-cup`,
`scotland-league-cup-group-c`, `england-amateur-u21-premier-league-cup-group-g`)
never resolving a competition id. `teams`, `standings`, `matches` and
`team_aliases` were all empty and had never held a row; the long-suspected
team-matching defect was this all along, because `/standings` fails before any
team is stored and `candidates=0` follows from an empty table. Pinning
`FOOTBALL_SEASON` to a supported season was rejected — it would show 2024/25
tables and form against 2026/27 fixtures, and silently wrong data is worse for
members than none.

With the provider `none`, `run_sync_football_data` takes its documented early
return: verified in production after the redeploy, the job logs `football data
sync skipped: no provider configured` and exits `0`. Reversing the decision is
one variable. Note the failed sweep cost **2 requests, not ~40** — api-football
does not charge plan-rejected calls against the daily allowance, so the
scheduler runbook's *"a failed run still spends what it sent"* is pessimistic for
this particular failure mode.

Redaction was confirmed end to end in production the same afternoon, after the
owner rotated the odds-api.io key — and the confirmation the previous session
promised ("production confirms on the next odds call") **would never have
arrived**, because `configure_logging` quiets `httpx` and `httpcore` to
`WARNING`, so a normal odds call emits no request line and therefore no
redaction marker. Zero markers is the correct steady state, not a pending gap.
What was run instead: one live `/leagues` call inside the production container
with the root handler's stream swapped for an in-memory buffer *before* the
request, so nothing could reach stdout either way. With `httpx` deliberately
forced back to `INFO`, the request line was emitted, the URL did carry
`apiKey=`, the raw key appeared **0** times and `<redacted>` appeared **1** time.
That call also proved the rotated key valid in production — 63 UK competitions
returned — which nothing had verified until then.

One verification the platform would not give: Railway's deployment list returns
only `createdAt`, `id`, `meta` and `status` for the newest entry, with no
`serviceInstance` snapshot, so the per-deployment replica/region/sleep metadata
could not be read back directly. It is attested instead by `railway.toml` (which
declares one replica in `europe-west4-drams3a`, sleep disabled, IPv6 egress on,
healthcheck `/api/v1/health/ready`), by `ci-local.sh`'s deployment-config
assertions passing against it, and by a live pre-deploy read of the running
service instance that matched exactly. CPU and memory limits are not declared in
`railway.toml` and read as `limitOverride: null` — plan defaults, not confirmed
as 0.25 vCPU / 500 MB.

The 2026-08-18 shipment carries Batch 31 (settlement cost) and Batch 32
(per-league notification mute, migration `013`) to production in one API
deployment, since neither had shipped before it. The Vercel CLI reported a
client-side `FetchError: … EPIPE` mid-upload; the deployment nonetheless
completed server-side, reached `Ready`, and already held the stable alias by
the time this was investigated — confirmed by fetching the live
`SettingsPage` chunk and finding Batch 32's `Per-league reminders` /
`league_mutes` strings in it, not by trusting the CLI's own exit status.
GitHub's auto-deploy of the same push had not fired after 20+ minutes, which
is why the explicit CLI path (section 4) was used rather than skipped.

The 2026-08-15 shipment closed a nine-day reporting gap rather than a drift.
Investigation that morning confirmed against Railway's GraphQL API that
`7a5862cb` was still current and carried `aae3b51e`, so the API had never fallen
behind; `/health` reported `sha: unknown` only because that image predated the
`/ship-prod` step that stamps `RAILWAY_GIT_COMMIT_SHA`. A blank `sha` is a
reporting gap, not evidence of drift — but it is indistinguishable from one from
the outside, which is why `/health` now also reports the migration head bundled
in the image. Since this shipment `/health` reports the exact commit and
`check-deploy-drift.sh` answers from tier 1: `in sync`, exit 0.

The 2026-08-16 Vercel deployment was **not** minted by `/ship-prod`. It is the
GitHub-linked auto-deploy of the same push, which already held the stable alias
by the time the API shipped; section 4 was skipped by design that day. The
2026-08-18 Vercel deployment, by contrast, *was* minted by `/ship-prod` — the
GitHub auto-deploy did not fire within the workflow's window, so section 4's
explicit CLI path ran instead (see above).

### 2026-08-22 — `82a7a120`, the three-bug fix (no migration)

Source commit `82a7a120`, on `origin/main`, gate green (`scripts/ci-local.sh`,
11 checks, 745 backend tests against real PostgreSQL) with a GitHub Actions
`Quality` run present and successful for the commit. **This shipment carried two
merges, not one:** Batch 64 (`5d2a9645`, the FotMob card cross-check) had merged
but never shipped, so the deployed API was still `a8866f32` from the Batch 63
shipment. Both reached production together.

Railway `5af73dae-58a3-4574-b28b-a70166fe04a3`, `SUCCESS`. Its predecessor —
this shipment's rollback baseline — is `b11eae41-ce5c-462b-a7c8-c1a4072e26a1`,
which was serving `a8866f32` at head `015`. **No Alembic revision**, so head
stays `015` and no forward recovery plan was required; `b11eae41` bundles the
same head and can boot.

Section 4 was skipped by design: the GitHub integration had already built
`82a7a120` as `dpl_CT48uzP7g4LA1VFp4ZhKDbr6eZ6k`, whose `githubCommitSha` was
read from the Vercel API rather than inferred from timing, and which already
held the stable alias. Its predecessor is `dpl_CPg2f2MLDACo7W4Y3xaxor8qcXei`.

Its content: three bugs reported from use. The first was **not a defect** —
every league is on `pick_scope = 'selection'`, where a claim takes one outcome
and the rest of the game stays open. The owner wants one member per game, which
is a settings change; what shipped is the bug that switching would have exposed.
The slate marked *every* selection on a game the caller holds as `mine`, so a
client greys out the whole game and the one member entitled to move between its
markets could not, while the "my pick" banner named whichever selection was
priced first. `_selection_options` now blocks only on a holder who is somebody
else, matching `_claim_conflict`, with the exact holder of a selection
outranking the fixture-level blocker — which matters because a league switched
from `selection` to `fixture` keeps rows written under the old rule. The other
two are web-only: both join paths left the cached `['leagues', 'mine']` list in
place, so a new member landed on "You're not in a league yet"; and Football
Stats ordered competitions differently from the coupon.

Post-deploy verification: `/health` reports sha `82a7a120` and migration `015`,
`/health/ready` agrees at `015` with `db: ok`, the deployment manifest confirms
exactly one replica in `europe-west4-drams3a` with serverless sleep disabled,
IPv6 egress enabled and healthcheck `/api/v1/health/ready` (`limitOverride:
null`, i.e. plan defaults rather than a pinned 0.25 vCPU / 500 MB), RLS is on
all 18 public tables with zero grants to `anon`/`authenticated`/`PUBLIC`, the
deployment log carries 0 genuine errors and 0 secret-leak hits, the stable web
root and a SPA deep link both return 200 with identical bytes and the three
committed headers, the CORS preflight from
`https://the-coupon-production.vercel.app` returns 200 with that exact origin
and credentials enabled, and `/api/docs` still 404s.

> **Log scanning reads `event`, not `message`.** structlog writes its content to
> `event` and leaves `message` empty, so a scan of `message` alone inspects none
> of the application's own lines — it silently passed over `scheduler started`
> and every apscheduler line here before the scan was widened to the whole
> record. Railway also tags uvicorn's and alembic's stderr as `level=error`, so
> six `INFO:` lines present as errors and are not. Scan whole records and
> classify by content, not by level.

> **The 2026-08-22 owner action is still owed** — rotate the production database
> password for `pugujiiojitstkilphrz` and update Railway's `DATABASE_URL`. This
> shipment's RLS recheck was run through an asyncpg client that never renders
> the DSN, so it did not repeat the exposure, but the leaked value is unchanged
> and still live.

### Current rollback baselines

Updated after the 2026-08-21 shipment of `1272dde` (Batches 47–48, no
migration).

| Stack | Roll back to |
| --- | --- |
| Railway `api` | `4b79e0a0-293f-4afd-a220-e00b346998d0`, the predecessor of the live `854a24ec`. **Available** — it bundles head `015`, the same head the database is stamped at, so it can boot. Stable until the next `/ship-prod`. |
| Vercel web | *The immediate predecessor of whatever is live* — read it, do not trust an id written here. As of 2026-08-21 11:41 that is `dpl_CyJqDtkZti7JA67KHYFu2HV6zG5v`, behind the live `dpl_FfGCr4FcbFaGnzaEzN33D6qAHFVE` — which is itself the docs commit recording this shipment, and will be superseded by the next push. Read the pair; do not trust these two ids. — and the commit recording this paragraph will already have superseded both. |

`4b79e0a0`, not the previously-recorded `8201bfac`, was the deployment actually
live immediately before this shipment. Between the 08-21 `16a64eff` shipment
recorded above and this one, Railway shows two further deployments at the same
commit and head (`da7acc90` at 08:20:34 and `a137f792` at 08:23:05, both
`reason: redeploy`, both now `REMOVED`) culminating in `4b79e0a0` at 08:28:04.
Same image, same commit, same migration head throughout — nothing shipped
between them — but the cause of the redeploys is not established from the
Railway API available here. Recorded rather than glossed, per the standing
rule that a written id is a snapshot, not a durable fact: read the live pair
before trusting either.

**The two rows age differently, and the Vercel one cannot be pinned.** The API
deploys only by CLI, so its baseline moves only when `/ship-prod` runs. The web
project is GitHub-connected and mints a production deployment on *every* push to
`main` — including doc-only and test-only commits that change no bundle. So the
Vercel id above is a snapshot with a timestamp, not a durable fact: the id this
section carried before (`dpl_3hX34stqNHZQQ7jeaqv9RNEek5re`) was two deployments
stale by the time anyone read it. Read the current pair before rolling back:

```bash
vercel ls the-coupon-production --prod --scope team_MVQMOaFtYHlwO5QVzSOZQ0Ud
```

Vercel marks only the two most recent production deployments
`isRollbackCandidate: true`, so in practice the target is always the immediate
predecessor and there is nothing to look up beyond those two.

**The API rollback is available, and the prediction pattern has now run twice.**
It goes absent whenever a migrating shipment lands, because rollback needs a
*second* deployment at the live head. It went absent at `013`, was restored by
Batch 35, went absent again when `014`/`015` shipped on 2026-08-20 leaving
`d0660dac` as the only image at head `015`, and the 2026-08-20 shipment of
Batches 43–45 restored it: that shipment applied no migration, so `5e6e522e`
(and `88c4885c` behind it) are further images at head `015`. **The next shipment
that migrates empties this row again**, and the one after that restores it.

The reason is the boot sequence, not the schema. `nixpacks.toml` starts with
`alembic upgrade head && uvicorn ...`, and an image ships only the migration
scripts that existed when it was built. Started against a database stamped `015`,
a pre-`014` image cannot resolve the revision at all — it fails with
`Can't locate revision identified by '015'`, the `&&` chain stops, uvicorn never
starts, and the healthcheck fails. **This holds regardless of what is in the
tables**, so it is not something a data fix can unlock. Do not attempt a Railway
rollback to `1765f0aa`, `492037b0`, `c5426392`, `f54fa403`, or anything older;
they will fail their healthcheck rather than serve. `5e6e522e` is safe for
exactly one reason — it bundles `015`.

One caveat this shipment added: `5e6e522e` is the **config-only** redeploy that
carries `FOOTBALL_DATA_PROVIDER=none`, so rolling back to it preserves the owner's
2026-08-20 decision. That is the right target for exactly that reason — see the
entry above about why `d0660dac` is not.

Where rollback is unavailable, recovery is forward-only per the approved plan for
`013` above: the feature is already off by default (`notification_muted = false`
everywhere), so there is no opt-in to clear; ship a corrected image at head `013`
or higher.

Note also that a `REMOVED` Railway deployment may have had its image pruned, and
`canRedeploy: true` is reported even for deployments that could not possibly
restore — it is not evidence of anything.

**Vercel rollback is unaffected and remains available.** The web app degrades
independently of the API, and the API is never behind it — `/ship-prod` deploys
the API from a commit `main` already carries — so an older bundle still finds
every field and endpoint it expects. Verified 2026-08-16; the mechanics of
picking the target are in the baselines table above.

Rollback reverts application deployments only. Under the 2026-07-30 backup
deferral there is no database restore path at all, so rollback must never assume
a recoverable database and never downgrades it. A migration incompatible with
the previous application requires a separately reviewed forward recovery plan,
written before the migration ships rather than after it fails — as was done for
`007`–`011` before the 2026-08-06 shipment, and for `012` before the 2026-08-16
one.

### Pre-migration snapshot, 2026-08-06

Because there is no backup, a targeted logical snapshot of the four tables `009`
rewrites (`leagues`, `gameweeks`, `fixtures`, `picks` — 134 rows) was taken
immediately before the shipment and kept outside the repository at
`~/the-coupon-snapshots/`. Note that `pg_dump` was unusable here: production runs
PostgreSQL 17.6, no SSL-capable `pg_dump` is installed on the operator's machine,
and the copy bundled with `pgserver` is both older and compiled without SSL. The
snapshot was taken over `asyncpg` instead.

### Forward recovery plan — migration `012`, Batch 27

**Status: reviewed and approved by the owner, 2026-08-16. Cleared to ship.**

Required by `/ship-prod` step 1.7 before `012` may be deployed. Production is at
head `011` (deployment `6fe96f0e`); this shipment moves it to `012`.

**No pre-migration snapshot is needed.** Unlike `009`, `012` rewrites no data: it
adds two nullable columns, one `CHECK`, and one enum value. Every existing row is
left byte-for-byte as it was, and `NULL` on both new columns is exactly the
pre-batch behaviour, which is why the migration carries no backfill.

**API rollback is unavailable the moment `012` applies, and not for a data
reason.** `nixpacks.toml` boots with
`alembic upgrade head && uvicorn ...`, and every pre-`012` image ships migration
scripts `001`–`011` only. Started against a database stamped `012`, that image's
Alembic cannot resolve the revision at all — it fails with `Can't locate revision
identified by '012'`, the `&&` chain stops, uvicorn never starts, and the
healthcheck fails. This is the fix-forward-only state the rollback baseline
section already predicted for the first shipment past `011`. It holds regardless
of what is in the tables, so **do not attempt a Railway rollback to a pre-`012`
deployment after this ships.** Vercel rollback is unaffected and stays available;
the web app degrades independently.

Recovery is therefore forward-only, in increasing order of cost:

1. **Disable the feature without deploying.** The whole batch is inert while no
   league opts in, so returning to pre-batch behaviour needs no code:

   ```sql
   UPDATE leagues   SET pick_open_offset_minutes = NULL;
   UPDATE gameweeks SET status = 'open' WHERE status = 'scheduled';
   ```

   The second statement is the same mapping `012`'s own downgrade applies, and
   the pre-batch reading of such a round: it exists, so it is claimable. The
   consequence is that members may claim earlier than an admin announced —
   degraded, not broken. Order matters: clearing the offsets first stops
   `sync_slate` writing new `scheduled` rows behind the second statement.

2. **Deploy a corrected image at head `012` or higher.** The normal path for an
   application defect. `012` stays applied.

3. **Never run `alembic downgrade` against production.** `012`'s downgrade
   rebuilds `gameweek_status` to drop `'scheduled'`, because PostgreSQL has no
   `DROP VALUE`. It is written for local and staging use and is not part of any
   production procedure.

**Data compatibility, for completeness.** Were the boot-migration problem solved
by other means, `012` is otherwise backward-compatible with the `011`
application: it ignores both new columns, and the `CHECK` exempts `NULL` on a
column it never writes. The single incompatibility is `gameweek_status` gaining
`'scheduled'`, which the `011` app's `StrEnum` cannot deserialise — but only rows
the *new* app writes can ever hold it, and only after an admin sets
`pick_open_offset_minutes` and a round is then discovered ahead of its opening.
Step 1 above clears exactly those rows.

### Forward recovery plan — migration `013`, Batch 32

**Status: reviewed and approved by the owner, 2026-08-18. Cleared to ship.**

Required by `/ship-prod` step 1.7 before `013` may be deployed. Production is at
head `012` (deployment `f54fa403`); this shipment moves it to `013`.

**No pre-migration snapshot is needed.** `013` adds one column,
`league_memberships.notification_muted` (boolean, `NOT NULL`, `server_default
false`). Every existing row is written `false` on the same additive terms as
`012`'s two nullable columns — no backfill, no data rewritten.

**API rollback is unavailable the moment `013` applies, and not for a data
reason** — the same boot-sequence fact recorded for `012`. `nixpacks.toml` boots
with `alembic upgrade head && uvicorn ...`, and every pre-`013` image ships
migration scripts `001`–`012` only. Started against a database stamped `013`,
that image's Alembic cannot resolve the revision at all — it fails with `Can't
locate revision identified by '013'`, the `&&` chain stops, uvicorn never
starts, and the healthcheck fails. This holds regardless of table contents, so
**do not attempt a Railway rollback to a pre-`013` deployment after this
ships.** Vercel rollback is unaffected and stays available.

Recovery is therefore forward-only, in increasing order of cost:

1. **Disable the feature without deploying.** The behavior is already fully off
   by default — `notification_muted` is `false` on every existing row, and
   nothing in this batch flips it except an explicit member action. If a row
   is muted incorrectly:

   ```sql
   UPDATE league_memberships SET notification_muted = false;
   ```

   Safe and reversible at the data level; it does not touch any other column.

2. **Deploy a corrected image at head `013` or higher.** The normal path for an
   application defect. `013` stays applied.

3. **Never run `alembic downgrade` against production.** `013`'s downgrade
   drops the column outright, which destroys any state written to it since —
   unlike `012`'s enum-remap downgrade, this one is not merely unused, it is
   actively destructive. It is written for local and staging use only.

**Data compatibility, for completeness.** Were the boot-migration problem
solved by other means, `013` is otherwise fully backward-compatible with the
`012` application: the old app never references the new column, reads or
writes it nowhere, so existing behavior is unaffected either way.

### Forward recovery plan — migrations `014` and `015`, Batches 41 and 42

**Status: reviewed and approved by the owner, 2026-08-20. Cleared to ship.**

Required before `014` and `015` may be deployed. Production is at head `013`
(confirmed directly, 2026-08-20); this shipment moves it to `015` — the first
two-revision shipment since `007`–`011`.

**No pre-migration snapshot is needed, and the database is small enough to say
so with confidence.** Measured 2026-08-20: 4 `gameweeks`, 2 `leagues`, 1
`profiles`, 1 `picks`.

* `015` adds one nullable column, `profiles.avatar_url` (varchar(500)), with no
  backfill — the same additive terms as `012` and `013`.
* `014` adds one nullable column, `gameweeks.number` (integer), **and unlike any
  migration before it, writes data**. That difference is worth naming rather
  than glossing: the `UPDATE` sets a column that did not exist a statement
  earlier, so it cannot destroy or overwrite anything. It touches 4 rows. No
  other column is read or written.

**API rollback is unavailable the moment `014` applies, and not for a data
reason** — the same boot-sequence fact recorded for `012` and `013`.
`nixpacks.toml` boots with `alembic upgrade head && uvicorn ...`, and every
pre-`014` image ships migration scripts `001`–`013` only. Started against a
database stamped `015`, that image's Alembic cannot resolve the revision at all,
the `&&` chain stops, uvicorn never starts, and the healthcheck fails. **Do not
attempt a Railway rollback to a pre-`014` deployment after this ships.** Vercel
rollback is unaffected and stays available.

Recovery is therefore forward-only, in increasing order of cost:

1. **Disable either feature without deploying.** Both are inert at the data
   level, and nulling the new column is a complete revert to pre-batch
   behaviour rather than a partial one.

   ```sql
   -- Batch 41: every surface falls back to the round's date, which is exactly
   -- what it showed before. `roundName` treats a missing number as "label by date".
   UPDATE gameweeks SET number = NULL;

   -- Batch 42: currently a no-op, because no avatar can be written — the upload
   -- endpoint fails closed with no storage backend configured.
   UPDATE profiles SET avatar_url = NULL;
   ```

   Neither statement touches another column, and neither affects locking,
   settlement or scoring: nothing in those paths reads either column.

2. **Deploy a corrected image at head `015` or higher.** The normal path for an
   application defect. Both revisions stay applied.

3. **Never run `alembic downgrade` against production.** Both downgrades drop
   their column outright. `015`'s is destructive in principle only (there are no
   avatar URLs to lose yet). `014`'s loses the numbering — recoverable in that
   the numbers are a pure function of `league_id` and `starts_on` and the
   migration's own backfill re-derives them, but a member who was told
   "Gameweek 3" would still see it change if rounds were deleted in between.
   Both downgrades are written for local and staging use only.

**Data compatibility, for completeness.** Were the boot-migration problem solved
by other means, both revisions are fully backward-compatible with the `013`
application: it references neither column, reads or writes them nowhere, so
existing behaviour is unaffected either way.

**One post-deploy check specific to `014`.** Confirm the backfill actually ran,
because a nullable column silently staying null looks identical to a feature
nobody has used yet:

```sql
SELECT count(*) AS unnumbered FROM gameweeks WHERE number IS NULL;  -- expect 0
```

### 2026-08-22 — `82a7a120` rows added retrospectively

The narrative for that shipment is the section above and was written at the
time; its **table rows were never added**, which is why the table appeared to
end at `b9e78fa` while production had moved on twice. Added here from the
section's own recorded IDs rather than re-derived. Nothing about the shipment
changed — only the index caught up with it.

The lesson is about this file, not that deploy: `/ship-prod` §1.8 reads the
rollback baselines from the platforms, so a stale table costs nothing at deploy
time and everything to a reader trying to work out what is live.

### 2026-08-24 — `df8304f`, the post-launch member-report set (**migration `016`**)

Source commit `df8304f`, on `origin/main`, gate green (`scripts/ci-local.sh`,
11 checks, 827 backend tests against real PostgreSQL) with a GitHub Actions
`Quality` run present and successful for the commit.

**Seven batches in one shipment** — 65, 66, 67, 69, 70, 71 and 72, the whole
post-launch set built from member reports on 2026-08-23. Batch 68 was held back
because it needed odds only the owner could evidence.

Railway `e2cbbf2d-0626-4fdb-b2c2-c348d97165d8`, `SUCCESS`. Its predecessor —
this shipment's rollback baseline — was
`5af73dae-58a3-4574-b28b-a70166fe04a3`, serving `82a7a120` at head `015`.

**This is the first shipment since `015` to carry an Alembic revision**, so
§1.7's forward-recovery-plan gate applied. The plan is
`docs/runbooks/migration-016-recovery.md`, written and shipped in the same
commit. Revision `016` drops `NOT NULL` from `profiles.pin_hash`: a
catalogue-only change that moves no data, and **forward-compatible with the
previous image**, because pre-Batch-66 code reads the column and never writes
`NULL`. That is the load-bearing property — `5af73dae` remains a bootable
rollback target and a rollback needs no `alembic downgrade`, unlike the `014`
case recorded above.

Section 4 was skipped by design, for the ninth time running: the GitHub
integration had already built `df8304f` as
`dpl_52QhjHArVNNyof4mFksBJuyFXVyz`, whose `githubCommitSha` was read from the
Vercel API rather than inferred from timing, and which already held the stable
alias.

Post-deploy verification: `/health` reports sha `df8304f` and migration `016`,
`/health/ready` agrees at `016` with `db: ok`, the boot log shows
`Running upgrade 015 -> 016` with no errors, and a 38-line bounded log review
found zero error or traceback lines and zero secret-shaped matches across
connection-string, JWT, bcrypt, private-key, long-token and key-assignment
patterns. `016` was confirmed in the database directly: `alembic_version` at
`016`, `profiles.pin_hash` `is_nullable = YES`, 13 active profiles and **0**
holding `NULL` — nobody stranded mid-reset. The stable web root and a deep link
return `200` with a byte-identical SPA asset and the committed security headers,
and an `OPTIONS` preflight from the exact stable origin returns `200` with
credentials enabled while a foreign origin is refused `400`. The new surface was
probed unauthenticated: every `/api/v1/admin/*` route answers `403` rather than
`404`, and `/auth/pin/set` answers `409` — shipped and gated.

**One trap fired during preflight and is worth recording.** A bare
`vercel list --prod` returned **the-coupon-staging**, silently, exactly as
§4 warns: `.vercel/project.json` points at staging. It was caught because the
output named the project, and redone with `VERCEL_ORG_ID` / `VERCEL_PROJECT_ID`
set. Nothing was acted on from the wrong reading.

### Forward recovery plan — migration `017`, Batch 83

**Status: approved by the owner, 2026-08-27. Cleared to ship.**

Required by `/ship-prod` step 1.7 before `017` may be deployed. Production is at
head `016` (deployment `a8ab5234`, serving `f41a383a`); this shipment moves it to `017`.

**No pre-migration snapshot is needed. `017` rewrites no data at all.** It drops
`uq_profiles_display_name` and creates `uq_profiles_display_name_lower`, a unique
index on `lower(display_name)`. Every row is left byte-for-byte as it was, no
column is added or removed, and no value is recomputed.

**This is the first migration here that can refuse to run, and that refusal is the
designed behaviour rather than a fault.** `017` begins by querying for profiles whose
names collide case-insensitively and raises a `RuntimeError` naming them if any exist,
because it cannot decide which of two real members is the survivor.

**Whether production holds such a pair was NOT verified before shipping.** It could
not be from the workstation: `db.pugujiiojitstkilphrz.supabase.co` publishes AAAA
records only and this Mac has no IPv6 route, and the project's REST API answers `402`
under the egress quota noted on 2026-08-25. The runtime check is what stands in for
that verification, which is why it names the rows rather than letting Postgres emit a
bare duplicate-key line into a container log.

**If the check fires, production is unaffected.** `nixpacks.toml` boots with
`alembic upgrade head && uvicorn ...`, so the abort stops the chain, uvicorn never
starts, the healthcheck never passes, and Railway keeps serving `a8ab5234` at head
`016`. The database is untouched — the check runs before any DDL. Recovery:

1. Read the deployment logs. The error names each colliding lowered name, how many
   profiles hold it, and their ids in `created_at` order.
2. Reach the database through `railway ssh` into the **running** (pre-`017`) container
   — the only path from here that can resolve the host — and rename all but one of
   each group. `profiles.display_name` has exactly three writers in the whole
   application (`routers/auth.py`'s registration, `src/seeds.py`, and Batch 74's
   `backfill_names_and_numbers.py`), so a hand-written `UPDATE` conflicts with nothing.
3. Redeploy. Nothing needs rebuilding; the same image now migrates cleanly.

**API rollback is unavailable the moment `017` applies**, on the same terms as `012`,
`013` and `014`/`015`: every pre-`017` image ships revisions `001`–`016` only, so
started against a database stamped `017` its Alembic fails with `Can't locate revision
identified by '017'` before uvicorn is reached. **Do not attempt a Railway rollback to
a pre-`017` deployment after this ships.** Vercel rollback is unaffected.

Recovery once `017` *has* applied is forward-only:

1. **There is no "disable the feature" step, because there is no feature to disable.**
   `017` only refuses a write the application already refuses in `/auth/register`'s
   case-insensitive pre-check. Nothing a member can do today succeeds before this
   migration and fails after it; the index changes what happens when two requests race,
   which is the defect it exists to close.
2. **Deploy a corrected image at head `018` or higher.** The normal path. If `018` ever
   needs to remove this index, it must use `op.drop_index("uq_profiles_display_name_lower")`
   — **not** `op.drop_constraint`, which will not find it. Postgres cannot express
   `UNIQUE (lower(col))` as a table constraint, so it is an index and only an index.
3. **Never run `alembic downgrade` against production.** `017`'s downgrade restores the
   case-sensitive constraint and drops the functional one, which is correct but
   reopens the race; it is written for local and staging use.

**Data compatibility, for completeness.** `017` is fully backward-compatible with the
`016` application were the boot-migration problem solved by other means: that
application writes `display_name` in three places, all of which already avoid
case-variant duplicates by their own logic, so the stricter index rejects nothing they
would legitimately attempt.

**One post-deploy check specific to `017`.** Confirm the index is actually present and
the old constraint is gone — an aborted migration and a successful one both leave a
database that answers queries, so `/health/ready` reporting `017` is the load-bearing
signal, not that the service is up.

### 2026-08-24 — `18dfb9f`, the Batch 68 backfill module (no migration)

Source commit `18dfb9f`, gate green (11 checks, 846 backend tests). Head stays
`016`, so no forward recovery plan was required and `e2cbbf2d` bundles the same
head and can boot.

Railway `5922cf17-1767-4ab8-b225-9c0d2fd6b44f`, `SUCCESS`; rollback baseline
`e2cbbf2d-0626-4fdb-b2c2-c348d97165d8`. Section 4 skipped again —
`dpl_ALgZHtgeDFXGVWD73m3rVH164txg` carried `18dfb9f`, confirmed from the Vercel
API. Post-deploy: `/health` reports `18dfb9f` at `016`, `/health/ready` agrees
with `db: ok`.

**This shipment exists to run something, not to change behaviour.** It carries
`apps/api/src/backfill_august_2026.py`, whose only purpose is one execution
against production; no route, job or read path changed. It is recorded as a
shipment because the container it produced is the one the backfill ran inside.

The backfill was then applied at **21:27 UTC**: 26 picks across three rounds of
`2-1-hibs`, two rounds created and one added to. Verified in the database — 36
settled picks, **0** mismatches against `round(odds × 10)`, no round left
pending — and hand-tallied against both bet365 slips, 24 legs, every line
agreeing. Details and the evidence attribution are in
`docs/backfills/2026-08-rounds.md`.

**Running a module inside the container needs the container's own environment,
and `railway ssh` does not give it to you.** The plain `python` is the Nix one
without the app's dependencies, and even `/opt/venv/bin/python` fails —
`greenlet` cannot load `libstdc++.so.6` — because `LD_LIBRARY_PATH` is set for
pid 1 and not for an ssh shell. Take it from `/proc/1/environ`, and **never
print that file**: it holds `DATABASE_URL`, both JWT secrets and the VAPID
private key. The working form is:

```bash
cd /app && export LD_LIBRARY_PATH=$(tr "\0" "\n" < /proc/1/environ \
  | grep "^LD_LIBRARY_PATH=" | cut -d= -f2-) \
  && PYTHONPATH=/app/apps/api /opt/venv/bin/python -m <module>
```

### The current rollback baselines

For the next `/ship-prod`, and to be confirmed live rather than trusted from
here (§1.8):

| Stack | Baseline | Commit | Head |
| --- | --- | --- | --- |
| Railway `api` | `a5728aa4-8ac2-4a69-8d56-aaed9b1b9e7d` | `18dfb9f` | `016` |
| Vercel web | `dpl_4omNbVGwXhBM8hRZAQ2cESTbND86` | `af50d22` | — |

The Vercel entry is a **docs-only** auto-deploy from the Batch 68 close-out. It
is the baseline anyway, because it is what currently holds the stable alias —
the same reason `5e6e522e-…` is recorded above rather than the shipment before
it.

**Every image from `e2cbbf2d` onward is bootable against head `016`, and so is
`5af73dae` before it** — see the migration-016 recovery plan. The rollback
target is not emptied by this shipment.

### 2026-08-25 — two config-only redeploys, avatar storage on and back off

**No commit shipped.** `18dfb9f` and head `016` throughout; only
`AVATAR_STORAGE` moved, which is why the Railway baseline above is now
`a5728aa4` rather than `5922cf17` — a config-only redeploy is still the
deployment a rollback lands on, per the avatar runbook.

| Deployment | Set to | Result |
| --- | --- | --- |
| `a5728aa4-8ac2-4a69-8d56-aaed9b1b9e7d` | `AVATAR_STORAGE=supabase` | `SUCCESS` 11:48 UTC |
| `691128d6` (live) | `AVATAR_STORAGE=none` | `SUCCESS` 11:52 UTC |

The flag worked and the feature still cannot: in the container `avatar_storage()`
returned `SupabaseAvatarStorage` with `enabled = True`, but the Supabase project
answers **402 `exceed_egress_quota`** on a read-only `GET /storage/v1/bucket`
with the service key, so every upload would have raised `AvatarStorageError` and
surfaced as a 502. Reverted the same day rather than leave a control mounted that
fails on every press. Detail and the ordering rule — clear the restriction, *then*
set the flag — are in `docs/runbooks/avatar-storage.md`.

**The restriction is on the project that also hosts the production database**
(`db.pugujiiojitstkilphrz.supabase.co`). Direct Postgres was unaffected at the
time — queries ran and `/health/ready` reported `db: ok` — but a project-level
egress restriction is a database risk before it is an avatar one, and it is
recorded here rather than only in the feature's runbook for that reason.

## Gate state

The three production stacks are provisioned, isolated, configured, deployed,
and healthy. Production Supabase has never been attached to MCP. Backup and
restore evidence is not part of this gate, under the owner's 2026-07-30
deferral recorded in `docs/launch/L0_PROJECT_IDENTITY.md`.

Closed on 2026-07-31: the Supabase production project exists, is migrated to
`004`, is locked down, has clean advisors, and its direct connection string is
sealed into Railway.

Closed on 2026-08-01: every one of the seventeen production variable names is
sealed, and a local dry-run proves the sealed Betfair material satisfies the
production configuration validator.

Closed on 2026-08-03: both stacks are deployed and healthy, the stable alias is
confirmed, readiness reports the database reachable over the sealed direct
endpoint, migration head is `004`, TLS and CORS behave correctly, deep links
resolve through the SPA shell, and a bounded log review found no secret
material.

Closed on 2026-08-03: the administrator bootstrap ran and is idempotent, the
production counts match, and login works end to end against the deployed API.

Closed on 2026-08-04: the Betfair probe ran at the owner's explicit direction.
Certificate login, keep-alive, slate retrieval, and Match Odds pricing all
pass, and the defect the probe exposed is fixed and covered by tests.

The gate is blocked on three remaining items:

1. **`BOTH_TEAMS_TO_SCORE` pricing.** Betfair listed no such market for the
   2026-08-08 slate. Re-probe closer to a target Saturday and confirm the
   market appears and is priced.
2. **Railway log attestation.** Only testable once `SCHEDULER_ENABLED` is
   restored to `true` and a scheduled refresh has contacted Betfair from the
   deployed service. The owner performs the scheduler restoration.
3. **Sufficient selections for the first live gameweek**, per the launch-timing
   constraint recorded above. Six selections cannot seat fifteen members.

One follow-up is not gate-blocking but must not be forgotten: the administrator
PIN is currently a known value and must be changed at first login.

> **Superseded, 2026-08-15.** Everything in this section that turns on Betfair
> is dated. Batch 7 replaced the Exchange with `odds-api.io` behind the
> `OddsProvider` port, and production has run `ODDS_PROVIDER=oddsapi` with
> `ODDS_API_KEY` sealed since 2026-08-04. In particular:
>
> - The warning that production runs the broken `BFIdentityResponse`
>   certificate-login code no longer applies. That code is not on the request
>   path for any provider production uses, and the 2026-08-06 shipment
>   (`aae3b51e`) carries the fix regardless.
> - Blocker 1 (`BOTH_TEAMS_TO_SCORE` pricing) and blocker 2 (log attestation via
>   a scheduled Betfair call) were both written against the Exchange. Re-state
>   them against `odds-api.io` before treating either as a gate.
>
> `SCHEDULER_ENABLED` has been `true` since 2026-08-04. Read **Shipment
> history** for what is actually deployed.

The second 2026-08-22 shipment is an unplanned hotfix, not a batch, and applies
**no migration** — head stays `015`, so `3de32d48-66f3-4df8-a1a4-548dbbf40e36`
remains usable as a rollback target. Rollback baselines were Railway
`3de32d48-66f3-4df8-a1a4-548dbbf40e36` and Vercel
`dpl_2wZLwfKo5tUostnfggM8JhanGvoH`. Section 4 was skipped by design for the
fifth time running: Vercel's GitHub integration had already built `b9e78fa` and
the stable alias resolved to `dpl_3hnnyDkhAzoasUgiodL7sRL3H1yN`, whose
`githubCommitSha` was read from the Vercel API rather than inferred from timing.
The commit touches only `apps/api`, so the web bundle is unchanged in substance.

Its content: `odds-api.io` publishes Bet365 under two bookmaker keys — `Bet365`
carrying the full book, and `Bet365 (no latency)` carrying only `ML` — and
`_bookmaker_markets` matched on exact then case-folded equality, so an event
served under the decorated key returned no markets and the pick screen showed
"Not priced yet" on a fixture that was priced the whole time. Measured against
the live card that morning: of 137 fixtures, 121 priced before the fix and 124
after, and all three recovered were Scottish Premiership — Falkirk v Hearts,
Rangers v St Mirren, and St Johnstone v Celtic, which were unpickable until
this shipped. The remaining 13 are dropped from `/odds/multi` by the provider
altogether and are genuine non-coverage rather than a matching failure.

Post-deploy verification: `/health` reports sha `b9e78fa` and migration `015`,
`/health/ready` agrees at `015` with `db: ok`, RLS is on all 18 public tables
with zero grants to `anon`/`authenticated`/`PUBLIC`, the deployment log carries
0 errors and 0 secret-leak hits, the stable web root and a SPA deep link both
return 200 with identical bytes, and the CORS preflight from
`https://the-coupon-production.vercel.app` returns 200 with that exact origin
and credentials enabled.

The third 2026-08-22 shipment is Batch 63, public self-serve registration, and
applies **no migration** — head stays `015`, so
`b96c15f4-2fdf-4f26-81ba-75b694af3765` remains usable as a rollback target.
Rollback baselines were Railway `b96c15f4-2fdf-4f26-81ba-75b694af3765` and Vercel
`dpl_6hXprLejKeChzHJf7vufuyfi7sD8`. New Railway deployment
`b11eae41-ce5c-462b-a7c8-c1a4072e26a1`, message `ship production a8866f3`.
Section 4 was skipped by design for the sixth time running: Vercel's GitHub
integration had already built `a8866f32` and the stable alias resolved to
`dpl_CFjitb9QW5hBf1FinfzuzMq157xk`, whose `githubCommitSha` was read from the
Vercel API rather than inferred from timing.

Its content: the product had no account-creation path at all, so sharing the
app's URL sent the recipient to a sign-in form they could never satisfy.
`POST /api/v1/auth/register` is now unauthenticated and returns the same token
pair login returns. This reverses part of L0's private-provisioning posture on
the owner's decision, recorded as ADR 0008 and amended into L0. Because the
endpoint is an unauthenticated write that creates a row, its controls are the
feature: `5/hour` on the proxy-aware client address, `PUBLIC_SIGNUP_ENABLED` as a
kill switch needing no deploy, and case-insensitive uniqueness that includes
soft-deleted rows.

Post-deploy verification: `/health` reports sha `a8866f32` and migration `015`,
`/health/ready` agrees at `015` with `db: ok`, RLS is on all 18 public tables
with zero grants to `anon`/`authenticated`/`PUBLIC`, the deployment log carries 0
real errors and 0 secret-leak hits, the stable web root and a SPA deep link both
return 200 with identical bytes and the three committed headers, and the CORS
preflight from `https://the-coupon-production.vercel.app` returns 200 with that
exact origin and credentials enabled. `POST /auth/register` answers 422 on a
deliberately invalid body where an absent route answers 404, confirming the
endpoint is live without creating an account.

> **Owner action owed — rotate the production database password.** During this
> shipment's RLS recheck, `psql` was handed `$DATABASE_URL` directly; it cannot
> parse the `postgresql+asyncpg://` dialect prefix the variable carries, and its
> error message echoed the **entire DSN, password included**, into an agent
> session transcript. The value is unchanged and still live. Rotate the Supabase
> database password for `pugujiiojitstkilphrz` and update Railway's
> `DATABASE_URL`. Recorded here rather than fixed because rotation needs the
> Supabase dashboard, exactly as the Batch 36 provider-key exposure was.
> The check itself was re-run through a client that never renders the DSN.

**The phase was closed on 2026-08-04.** `docs/LAUNCH_PLAN.md` is the canonical
record and carries the tick. This line previously read that the phase remained
unchecked pending `/launch-verify L4` and `/launch-closeout L4`, which was true
when written and went stale at close-out. Corrected rather than deleted because
`/ship-prod` §1.2 requires L4 to be checked and a reader confirming that gate
lands here.

`apps/api/src/config.py` fails closed in production on empty `bf_app_key`,
`bf_user`, `bf_pass`, `bf_cert_file`, or `bf_key_file`. The successful
deployment above is therefore also evidence that all five are correctly sealed
and that the certificate pair materializes at its fixed runtime paths.

The 2026-08-26 shipment carries **Batches 61, 73, 74, 75 and 76** and applies **no
migration** — head stays `016`, which keeps
`691128d6-619f-4b8c-949c-af3667c6e50b` usable as a rollback target rather than merely
recorded as one. Section 4 was skipped by design for the fifth time running: Vercel's
GitHub integration had already built `a7573e32` and the stable alias resolved to
`dpl_6co4m3VtCnLMz1JPJY5GYdXUiezH`, confirmed by reading `meta.githubCommitSha` from the
Vercel API rather than inferred from timing.

**Its preflight found this table stale, exactly as the warning above predicts.** The
record named `5922cf17-1767-4ab8-b225-9c0d2fd6b44f` as current, but that deployment is
`REMOVED`: two redeploys on 2026-08-25 — `a5728aa4` and then `691128d6`, both of `18dfb9f`
with no new commit — were never written down. Both are backfilled above. The baseline used
for this shipment was read from the platform, not from here.

Content: the FastAPI 0.141 / starlette 1.6 / pydantic 2.13 upgrade, a round badge that
reads the clock rather than `status`, the 2-1 Hibs renumber-and-rename backfill (applied
separately at 06:13 UTC, before this deployment), the removal of the nightly `pg_dump`, and
three new notification triggers with the per-league mute gate underneath them.

Post-deploy verification: `/health` reports sha `a7573e32` and migration `016`,
`/health/ready` agrees at `016` with `db: ok`, RLS **and FORCE RLS** are on all 18 public
tables with zero grants to `anon`/`authenticated`/`PUBLIC`, and the CORS preflight from the
stable origin returns 200 with credentials while `https://evil.example` gets 400 and no
`Access-Control-Allow-Origin`. The web root and a SPA deep link both return 200 and serve a
byte-identical asset, carrying all three committed headers. The boot log shows
`scheduler started`, **no `daily_backup` job** (Batch 75) and `pick_reminders` present
(Batch 76); its six `level=error` records are all uvicorn/alembic stderr reading `INFO:`,
the documented Railway misclassification, and a content scan found zero real errors and no
credential, connection-string, token or PIN leakage.

**A new interaction this runbook predates.** Section 3 notes that a stalled deployment runs
two containers, both with `SCHEDULER_ENABLED=true`, and that the *daily 11:00* pick
reminders would double-notify. Batch 76 moved reminders to **hourly at `:15`**, which
widens that window from once a day to once an hour — though it also narrows the blast
radius, since the job now only matches rounds locking in about three hours. This shipment
was unaffected: it reached `SUCCESS` in ~90 seconds and no league had a round in the
reminder window.

### 2026-08-27 — `3cb8b4f1`, Group A of the 2026-08-26 review (Batches 82–85)

Source commit `3cb8b4f1`, gate green (11 checks) and a GitHub `Quality` run confirmed to
**exist** for the commit rather than merely not to have failed. Head moves `016` → **`017`**,
so `a8ab5234-06c2-41d3-8358-405d95910d15` — the recorded rollback baseline — **is now
unusable**: a pre-`017` image ships revisions `001`–`016` only and its Alembic cannot
resolve `017`, so it would fail before uvicorn. Recovery is forward-only, per the plan
above. Vercel rollback is unaffected.

Railway `caeb17c2-732c-4195-9322-e7b84e7db3d8`, `SUCCESS`. Section 4 was skipped by design
again: `dpl_AA5mjrASLwSikRYYxuYHtC1Xajcm` already held the stable alias and its
`githubCommitSha` reads `3cb8b4f1c562211118ce1c1a5a18e43104611e45`, read from the Vercel
API rather than inferred from timing.

Content is the API half of the 2026-08-26 review's Group A: an authenticated SSRF closed
at `POST /push/subscribe` (the review's only HIGH), the display-name uniqueness backstop
made case-insensitive, a league window refused when it would land on the clock-change hour,
and the fourth notification trigger brought under the per-league mute.

**`017` was shipped without its precondition verified, deliberately and with a stated
fallback.** Whether two production profiles already collided case-insensitively could not
be checked beforehand — `db.pugujiiojitstkilphrz.supabase.co` publishes AAAA records only
and the workstation has no IPv6 route, and the project's REST API answers `402` under the
egress quota. The migration's own pre-flight check was the mitigation. **It passed: the
upgrade ran, so no collision existed.** Confirmed afterwards from inside the container —
`uq_profiles_display_name_lower` present, `uq_profiles_display_name` gone, and the
collision query returns 0.

Post-deploy verification: `/health` reports sha `3cb8b4f1` and migration `017`,
`/health/ready` agrees at `017` with `db: ok`; RLS is on all 18 public tables with **zero**
grants to `anon`/`authenticated`/`PUBLIC`; the web root and a deep link serve one identical
SPA asset (matching SHA-256) carrying all three committed headers; a preflight from the
stable origin returns 200 with the exact origin and credentials enabled while a foreign
origin is refused with 400; `/api/docs` 404s; and two bounded log snapshots showed a clean
`Running upgrade 016 -> 017`, uvicorn and the scheduler up, zero failure-shaped lines and
zero matches across six secret-leakage patterns.

**The 0.25 vCPU / 500 MB limits were again not verified** — the same dead end recorded on
2026-08-26. `railway.toml` does not declare them and the GraphQL schema reachable from the
CLI rejects `cpuLimit`/`memoryLimit` on `serviceInstance`. Everything `railway.toml` *does*
declare verified against the deployment manifest: one replica in `europe-west4-drams3a`,
`sleepApplication: false`, `ipv6EgressEnabled: true`, healthcheck `/api/v1/health/ready`
with a 300s timeout.

**Batch 82's validation was not probed in production.** Exercising `/push/subscribe` needs
an authenticated account and writes a row, which is outside what may be run against
production here; it is covered by 17 gate tests instead.

### 2026-08-28 — `359c08f1`, Group C of the 2026-08-26 review (Batches 89–90), plus Group B

Source commit `359c08f1`, on `origin/main`, gate green (`scripts/ci-local.sh`, 11 checks)
re-run on the shipping commit itself, with a GitHub `Quality` run confirmed to **exist** for
the commit and to have concluded `success`. **No Alembic revision** — head stays `017`, so
no forward recovery plan was required and, unlike the previous shipment, the recorded
rollback baseline is genuinely bootable: `caeb17c2-732c-4195-9322-e7b84e7db3d8` bundles the
same head.

Railway `9cc1ef2a-a108-4066-84c1-a1626a1b0c71`, `SUCCESS`. Its predecessor — this
shipment's rollback baseline — is `caeb17c2-732c-4195-9322-e7b84e7db3d8`, which was serving
`3cb8b4f1` at head `017`.

Section 4 was skipped by design. Vercel's GitHub integration had already built `359c08f1`
as `dpl_9sYVZMb9X945VjpLgsHtSKXpKSGs`, which already held the stable alias; confirmed by
filtering production deployments on `githubCommitSha` through the CLI rather than inferring
it from timing. Its predecessor is the Vercel rollback baseline.

**This shipment carried more than its own group.** Batches 86, 87 and 88 (Group B, web-only)
had reached members through Vercel days earlier but had never been part of a Railway
shipment, because none of them touched the API. Only Batch 89 moves the deployed image.

Content: **Batch 89** closes OPS-10/CORR-03 — `POST /leagues/{slug}/picks` now charges a
shared `50/hour;100/day` bucket keyed on the league, alongside the existing per-member
`10/hour`, and answers `429 PICKS_BUSY` when a league's share is gone. Fifty is both what
the hour leaves after the measured peak browsing hour and `max_members`'s own ceiling, so a
full league can still take one pick each. The bucket bounds a league and not the
installation; that residual is asserted in `test_request_budget.py`. **Batch 90** is the
client half and is web-only: pick submission now distinguishes a request that never left
the device (queued, flushed on reconnect) from one that left unanswered (unconfirmed, never
re-sent — reconciled by reading the round's pick back).

**The API/web gap this group was cut to avoid was real but never member-visible.** Batch
90's `PICKS_BUSY` copy went live on its close-out push while the deployed API could not yet
send that code, so the mapping was unreachable rather than wrong. The reverse ordering —
89 shipping first — would have shown members a raw error code.

Post-deploy verification: `/health` reports sha `359c08f1` and migration `017`,
`/health/ready` agrees at `017` with `db: ok`; the deployment manifest confirms one replica
in `europe-west4-drams3a`, `sleepApplication: false`, `ipv6EgressEnabled: true`, healthcheck
`/api/v1/health/ready` at 300s (`limitOverride: null` again — the 0.25 vCPU / 500 MB dead
end recorded on 2026-08-26 and 2026-08-27 is unchanged); RLS is on all 18 public tables with
**zero** grants to `anon`/`authenticated`/`PUBLIC` and the database reports head `017`; the
web root and a SPA deep link both return 200 with an identical asset (matching SHA-256) and
all three committed headers; a preflight from the stable origin returns 200 with that exact
origin and credentials enabled while a foreign origin is refused with 400; `/api/docs`
404s; and two bounded log snapshots (38 then 48 records, whole-record scans) show uvicorn
and the scheduler up, zero failure-shaped lines and zero matches across five
secret-leakage patterns.

> **`railway ssh` cannot run the app's own SQLAlchemy engine**, so the RLS recheck could not
> reuse it: greenlet fails to load in that shell (`libstdc++.so.6: cannot open shared object
> file`) even though the running process is fine. Raw `asyncpg` then failed three times with
> `CantChangeRuntimeParamError: parameter "ssl" cannot be changed now` — Railway's
> `DATABASE_URL` carries `?ssl=require`, and raw asyncpg forwards unknown query parameters as
> *server settings* while SQLAlchemy's dialect translates them. Strip the query string and
> pass `ssl=` as a real argument. The DSN was never rendered at any point.

> **`railway api` has no `deployment(id:)` field.** Polling with one silently returned an
> empty status for ten minutes while the deployment was in fact progressing normally to
> `SUCCESS`. Poll with `deployment list --limit N --json` and read the row, as section 3
> already says; a query that returns nothing looks exactly like a stalled deploy.

**The 2026-08-22 owner action is still owed** — rotate the production database password for
`pugujiiojitstkilphrz` and update Railway's `DATABASE_URL`. This shipment's RLS recheck ran
inside the container through a client that never renders the DSN, so it did not repeat the
exposure.

### Forward recovery plan — migration `020`, Batch 93

**Status: approved by the owner, 2026-08-30. Cleared to ship.**

Required by `/ship-prod` step 1.7 before `020` may be deployed. Production is at head `019`
(deployment `7ed1dc1e-7a44-46ab-9325-d58a25679133`, `SUCCESS`, serving `bc8c8191`); this
shipment moves it to `020` and carries Batches 93 and 94.

**No pre-migration snapshot is needed. `020` rewrites no data at all.** It is one statement
— `ALTER TYPE action_type ADD VALUE IF NOT EXISTS 'display_name_changed'` — which defines a
value and nothing more. No table is touched, no column added or removed, no row rewritten,
no value recomputed. It is the same shape as `019` (Batch 101) and as `012`'s `'scheduled'`.

**It cannot refuse to run.** Unlike `017` there is no precondition it checks and no state of
the data that makes it fail. `ADD VALUE IF NOT EXISTS` is also idempotent, so a retried boot
is harmless.

**API rollback is unavailable the moment `020` applies**, on the same terms as `012`, `013`,
`014`/`015`, `017` and `019`: every pre-`020` image ships revisions `001`–`019` only, so
started against a database stamped `020` its Alembic fails with `Can't locate revision
identified by '020'` before uvicorn is reached. **Do not attempt a Railway rollback to a
pre-`020` deployment after this ships.** Vercel rollback is unaffected. The recorded
baseline `7ed1dc1e` is therefore a record, not a usable target.

Recovery once `020` *has* applied is forward-only:

1. **Deploy a corrected image at head `020` or higher.** The normal path.
2. **Disabling Batch 93's behaviour needs no migration.** The notice is sent by a
   `lifespan` hook (`src/main.py::_send_pending_rename_notices`) calling
   `services/rename_notice.send_rename_notices`. Removing that one `await` stops it
   entirely; the enum value and any rows already written stay valid and inert.
3. **Never run `alembic downgrade` against production**, and this migration's downgrade is
   more costly than `019`'s. It rebuilds the type without the value and maps any
   `display_name_changed` row to `player_pin_reset`. Two consequences, both specific:
   those rows are Batch 93's **idempotency markers**, so rewriting them lets the next boot
   notify those members a second time; and Batch 94's new league Activity screen would then
   show them a "PIN reset" that never happened, for a member whose PIN was never reset.
   The downgrade is written for local and staging use.

**Forward-compatibility hazard, stated because it is the one real trap here.** The `019`
application's Python `ActionType` has no `display_name_changed` member, and `AuditLog`
maps the column through `Enum(ActionType, ...)`. If a `019` image were ever run against a
`020` database *after* the first marker row is written, the site-admin dashboard — which
reads `audit_log` globally and unfiltered — would fail to coerce that row. This only
matters on a rollback that is already ruled out above, but it means the rollback is not
merely blocked by Alembic: it would also be wrong.

**Data compatibility otherwise.** `020` is fully backward-compatible with the `019`
application until a row using the new value exists. Nothing in the `019` image writes one.

**Post-deploy checks specific to this shipment**, beyond the standard `/health` and
`/health/ready` agreement at `020`:

1. **Batch 93's boot task is the first thing this deployment does that is new and
   observable.** Read the bounded log snapshot for `rename notice delivered` (with a
   `pushes` count) or `rename notice undelivered, will retry next boot`, one line per member
   found. Three "undelivered" lines is a **correct** result if those members have no active
   push subscription — it means the marker was deliberately not written and the next boot
   will try again. No lines at all means the three profiles were not found by name, which
   would be a genuine defect and should be investigated before the next deploy.
2. **Batch 94's route must answer.** Its page reached members on the close-out push and has
   been calling `GET /api/v1/leagues/{slug}/audit-log` against an image that does not serve
   it. Confirm the route exists after the ship (a `401`/`403` from an unauthenticated probe
   is the correct answer; a `404` means it did not ship).

### 2026-08-30 — `f2d3efd9`, Group E of the 2026-08-26 review (Batches 91, 93, 94)

Source commit `f2d3efd9`, on `origin/main`, gate green (`scripts/ci-local.sh`, 11 checks)
re-run on the shipping commit itself, with a GitHub `Quality` run confirmed to **exist** for
that commit and to have concluded `success`. **Alembic revision `020`**, so the forward
recovery plan above was required and was approved before deploying.

Railway `f28224cd-ef2e-47d1-8112-33c14974fb53`, `SUCCESS`. Its predecessor —
`7ed1dc1e-7a44-46ab-9325-d58a25679133`, which was serving `bc8c8191` at head `019` — is
recorded as this shipment's baseline but **is not a usable rollback target**: a pre-`020`
image cannot boot against a database stamped `020`. Recovery is forward-only, per the plan.

Section 4 was skipped by design. Vercel's GitHub integration had already built `f2d3efd9`
as `dpl_FFbkoGNsPfiWDGnhjCLfgkKszznG`, which already held the stable alias; confirmed by
filtering production deployments on `githubCommitSha` through the CLI
(`vercel list --prod --meta githubCommitSha=<sha>`) rather than inferring it from timing.
Its predecessor `dpl_Hy1TwvdAgtcbvE46xkoAvHTUjvdR` is the Vercel rollback baseline, which is
unaffected by the migration.

Content: **Batch 91** makes a new league invite-only unless its creator says otherwise, and
explains each option at the point of choice — web-only, and live since 2026-08-30 on its own
close-out push. **Batch 93** tells the three members Batch 74 renamed that their sign-in name
changed, once, from a `lifespan` hook whose idempotency marker is an `audit_log` row
(`display_name_changed`, migration `020`). **Batch 94** gives a league admin the audit trail
of their own league — `GET /api/v1/leagues/{slug}/audit-log` behind `LeagueAdminDep`, plus
the Activity page.

**Batch 94's asymmetry was real and member-visible, which is why this shipment was not
deferred.** Its page reached members on the close-out push and called a route the deployed
image did not serve, so the Activity item 404'd for every league admin between close-out and
this ship. The sequencing document cut Group E specifically so that gap would not span a
boundary; running 94 last and shipping immediately is what kept it to minutes.

Post-deploy verification: `/health` reports sha `f2d3efd9` and migration `020`,
`/health/ready` agrees at `020` with `db: ok`; the deployment manifest confirms one replica
in `europe-west4-drams3a`, `sleepApplication: false`, `ipv6EgressEnabled: true`, healthcheck
`/api/v1/health/ready` at 300s; RLS is enabled **and forced** on all **19** public tables
(18 until migration `018` added `rate_limit_counters`) with **zero** grants to
`anon`/`authenticated`/`PUBLIC`, and the database reports head `020`; the web root and the
new `/leagues/:slug/admin/audit-log` deep link both return 200 with an identical asset
(matching SHA-256 `957b699e…`) and all four committed headers; a preflight from the stable
origin returns 200 with that exact origin and credentials enabled while a foreign origin is
refused with 400; `/api/docs` 404s; and a bounded log snapshot (45 records, whole-record
scans) shows uvicorn and the scheduler up, zero failure-shaped lines and zero matches across
five secret-leakage patterns.

**Two checks specific to this shipment, both passed.**

1. **Batch 94's route answers.** An unauthenticated `GET /api/v1/leagues/test/audit-log`
   returns `401` where it returned `404` before the ship, while a genuinely absent route on
   the same prefix still returns `404` — so the `401` is the route existing, not a blanket
   auth wall.
2. **Batch 93's boot task ran, and its partial result is the correct one.** The log shows
   **three** members located, **two delivered**, **one undelivered**; the database holds
   exactly **two** `display_name_changed` markers. The unreached member has no marker on
   purpose — they have no active push subscription, have therefore not been told, and the
   next boot will try again. Three located rules out the "no lines at all" defect the plan
   named. **Do not treat the missing third marker as a fault**; treat a marker count that
   stops changing while that member acquires a subscription as one.

> **`railway ssh`'s default `python` is the nix interpreter, not the app's.** `python3`
> resolves to `/nix/var/nix/profiles/default/bin/python3`, which has no `asyncpg`, so the
> RLS recheck fails with `ModuleNotFoundError` that looks like a missing dependency in the
> image. The application's environment is **`/opt/venv/bin/python`** (`/app` is the working
> directory, `/opt/venv` the venv). Use it, and keep stripping the `DATABASE_URL` query
> string and passing `ssl="require"` as a real argument, per the 2026-08-28 note. The DSN
> was never rendered at any point.

> **Railway now warns that Config as Code is deprecated.** `railway.json` / `railway.toml`
> are superseded by `.railway/railway.ts`, and the CLI states existing files keep working
> until **2026-12-01**. `railway.toml` is asserted by the deployment-config gate, so
> migrating it is a batch of its own and was deliberately not folded into this shipment.

### 2026-08-30 — `56348276`, Group F of the 2026-08-26 review (Batch 96)

Source commit `56348276`, on `origin/main`, gate green (`scripts/ci-local.sh`, 11 checks)
re-run on the shipping commit itself, with a GitHub `Quality` run confirmed to **exist** for
that commit and to have concluded `success`
(`https://github.com/CraigR973/the-coupon/actions/runs/33306219944`).

**No Alembic revision.** The repository's sole head is `020`, production was already at
`020`, and `git diff f2d3efd9..HEAD -- migrations/` is empty — so preflight step 1.7's
forward-recovery-plan requirement did not apply and no owner approval was sought. The boot
log confirms it: `alembic upgrade head` printed its context lines and **no `Running upgrade`
line at all**, which is what a no-op migration pass looks like.

**This is the shipment that restores a usable API rollback baseline.** Since Group C every
shipment has applied a migration, leaving the recorded baseline unbootable — a pre-`N` image
cannot locate revision `N` before uvicorn is reached. This one applies none, so its baseline
`f28224cd-ef2e-47d1-8112-33c14974fb53` (serving `f2d3efd9` at head `020`) runs against the
same `020` database the new image does and **is a genuine rollback target**.

Railway `7ec86030-9877-434f-beab-f4e942d7c14e`, `SUCCESS`, message `ship production 5634827`.
Rollback baseline `f28224cd-ef2e-47d1-8112-33c14974fb53`, as above.

Section 4 was skipped by design. Vercel's GitHub integration had already built `56348276` as
`dpl_CgBotjod5ae1Cdy8A2y9GsucqHvc`, which already held the stable alias; confirmed by
filtering production deployments on `githubCommitSha` through the CLI
(`vercel list --prod --meta githubCommitSha=<sha>`) rather than inferring it from timing.
Its predecessor `dpl_FMgyZzio1yiHCcyBnc3tDtyeuZkd` (carrying `14b7785c`, confirmed the same
way) is the Vercel rollback baseline.

Content: **Batch 96** gives standings a season boundary and an archive. `standings_by_league`
aggregated every settled pick a league had ever played while calling the result a "Season
table"; it is now bounded by `season_bounds` over `season_for` — the definition round
numbering already uses — with `season` defaulting to the one being played and any other
season read through the same ranking rule. `GET /leagues/{slug}/seasons` is the archive index
and `?season=` on the standings route reads a past table. The web half shipped on the
close-out push at 11:20 and the API followed at 11:29.

**The asymmetry window was benign, and that was by design rather than by luck.** For nine
minutes the leaderboard was drawing a season-bounded screen against an unbounded API. Nothing
broke: `/seasons` 404'd, the season strip hides itself on an empty seasons list, and the
standings request carried no `season` parameter, which the old image ignored. Members saw
exactly the screen they saw before. That is the opposite of Batch 94's gap, where the page
called a route the image did not serve and 404'd in front of every league admin.

Post-deploy verification: `/health` reports sha `56348276` and migration `020`,
`/health/ready` agrees at `020` with `db: ok`; the deployment manifest confirms one replica
in `europe-west4-drams3a`, `sleepApplication: false`, `ipv6EgressEnabled: true`, healthcheck
`/api/v1/health/ready` at 300s, restart `ON_FAILURE` ×3; RLS is enabled **and forced** on all
**19** public tables with **zero** grants to `anon`/`authenticated`/`PUBLIC`, and the database
reports head `020`; the web root and the `/leagues/:slug/leaderboard?season=2025` deep link
both return 200 with an identical asset (matching SHA-256 `10b8896b…`) and the committed
security/cache headers; a preflight from the stable origin returns 200 with that exact origin
and credentials enabled while a foreign origin is refused with 400; and two bounded log
snapshots (49 then 53 records, whole-record scans) show uvicorn and the scheduler up, zero
tracebacks, zero 5xx served, and zero matches across six secret-leakage patterns.

**One check specific to this shipment, passed.** An unauthenticated
`GET /api/v1/leagues/test/seasons` returns `401` where it would have returned `404` before
the ship, while a genuinely absent route on the same prefix (`/leagues/test/not-a-route`)
still returns `404` — so the `401` is the new route existing, not a blanket auth wall.

> **Railway's log stream tags stderr as `level: "error"`.** Six lines in this deployment's
> snapshot matched an error-level filter and every one of them was an `INFO` message —
> alembic's `Context impl PostgresqlImpl`, uvicorn's `Application startup complete`, and so
> on — because uvicorn and alembic both log to stderr. Read the message body before treating
> an error-level count as a finding; a raw count is not a signal here.

> **The service's CPU and memory caps are not queryable through the `ServiceInstance` GraphQL
> type.** `cpuLimit`, `memoryLimitGb` and `multiRegionConfig` are all rejected as unknown
> fields on that type, so the 0.25 vCPU / 500 MB caps were **not** independently re-confirmed
> this shipment. The replica count, region, sleep, IPv6 egress and healthcheck all *are* in
> the deployment manifest and were checked there.

### 2026-09-04 — `9e91b60`, Batch 104 (Railway config → IaC) + web Batches 92/97/98/103

Source commit `9e91b60` (`9e91b604e2041b3f2a46cddf9af1003442cba716`), on `origin/main`,
gate green — `scripts/ci-local.sh` re-run on the shipping commit, 11/11 checks including the
deployment-config assertions in their **new** `.railway/railway.ts` form — with a GitHub
`Quality` run confirmed to **exist** for the commit and to have concluded `success`
(`https://github.com/CraigR973/the-coupon/actions/runs/33860528054`).

**No Alembic revision.** The repository's sole head is `020`, production was already at
`020`, and `git diff 5634827..HEAD -- migrations/versions` is empty — so preflight step 1.7's
forward-recovery-plan requirement did not apply. The boot log confirms it: `alembic upgrade
head` printed only its context lines and **no `Running upgrade` line**. Of the five batches
carried, only **Batch 104** owes a `/ship-prod`; 92, 97, 98 and 103 are web-only and were
already live from their close-out pushes.

**This is the first Railway IaC apply against production.** `railway config plan` under
Node 22 (`.railway/railway.ts`, exact IDs supplied as `RAILWAY_PROJECT_ID` /
`RAILWAY_ENVIRONMENT_ID` / `RAILWAY_SERVICE_ID`) returned **`0 to add, 2 to change, 0 to
destroy`**, `"destructive": false`, both changes `"severity": "safe"`, `"kind":
"resource.update"`, touching only `service.api`:

- `build.builder` `RAILPACK` → `NIXPACKS`, `build.nixpacksConfigPath` `null` → `nixpacks.toml`;
- `deploy`: `healthcheckPath` → `/api/v1/health/ready`, `healthcheckTimeout` → `300`,
  `ipv6EgressEnabled` `false` → `true`, `limitOverride.containers` `null` → `cpu 0.25` /
  `memoryBytes 500_000_000`, `numReplicas` → `1`, `restartPolicyType` → `ON_FAILURE`,
  `restartPolicyMaxRetries` → `3`, `sleepApplication` → `false`, `multiRegionConfig`
  `{ ams: { numReplicas: 1 } }` → `{ "europe-west4-drams3a": { numReplicas: 1 } }`.

Every one of those aligns the persistent service-settings layer with the invariants the
running deployment already used through `railway.toml` at deploy time — the `before` values
(`ams`, `ipv6EgressEnabled: false`) were the dormant service-override layer, never what the
container ran. **No variable change appeared in the plan**: every `preserve()` entry —
including the eight `BF_*` names that are not set in production — produced no diff, so
nothing was deleted. Applied with `railway config apply --plan <pinned> --yes`, no
`--confirm-destructive`, and the plan file removed afterward. `railwayConfigFile` was `null`
before and after — no legacy Config File setting competes with the IaC graph.

The apply minted redeploy `85495b74-1190-4669-a902-3201731a72f4` (rebuilding the prior
source `56348276`); polled to `SUCCESS` before the source upload, and `/health` stayed green
at `56348276` / `020` throughout. It is now `REMOVED`.

`RAILWAY_GIT_COMMIT_SHA` was then stamped to `9e91b604…` with `--skip-deploys`, the worktree
re-checked clean, and `railway up` ran with every selector explicit: deployment
`e95ff966-f7ee-4587-999f-5470063ef108`, `SUCCESS`, message `ship production 9e91b60`,
`imageDigest sha256:62212ba6f492cd68a5d4ac362f112aa31dc1cdd92dc906955a4b6b5bd0bd18ce`. The
`deploymentEvents` breakdown shows `SNAPSHOT_CODE`, `BUILD_IMAGE`, `CREATE_CONTAINER`,
`HEALTHCHECK` (completed, not null), `CONFIGURE_NETWORK` and `DRAIN_INSTANCES` all with a
real `completedAt` — a clean promotion, no stall.

**Railway rollback baseline: `7ec86030-9877-434f-beab-f4e942d7c14e`** — the deployment live
immediately before this shipment, serving `56348276` at head `020`. This shipment applies no
migration, so that image boots against the same `020` database and **is a genuine target**.

Section 4 was skipped by design. Vercel's GitHub integration had already built `9e91b60` as
`dpl_HT3cQUVrofBAZB8Q1RG7q2XcYPAc` (immutable
`the-coupon-production-5t8ihoowf-craigr973s-projects.vercel.app`), which already held the
stable alias `https://the-coupon-production.vercel.app` — confirmed with
`vercel list --prod --meta githubCommitSha=<sha>` rather than inferred from timing. Its
predecessor `dpl_B5WD8nwNzAjhKeMyV92doWgoiVFq` is the **Vercel rollback baseline**.

Post-deploy verification: `/health` reports sha `9e91b604…` and migration `020`,
`/health/ready` agrees at `020` with `db: ok`. The deployment manifest
(`deployment.meta.serviceManifest`) confirms `numReplicas: 1`, `multiRegionConfig:
{ "europe-west4-drams3a": { numReplicas: 1 } }`, `sleepApplication: false`,
`ipv6EgressEnabled: true`, `healthcheckPath: /api/v1/health/ready` at `300`,
`restartPolicyType: ON_FAILURE` ×3, **and `limitOverride.containers` `cpu 0.25` /
`memoryBytes 500000000` — the 0.25 vCPU / 500 MB caps are independently confirmed from the
manifest this shipment, because the IaC `limitOverride` now bakes them in** (previous
shipments could only attest them via `railway.toml`). An in-container RLS recheck over an
asyncpg session (`/opt/venv/bin/python`, `DATABASE_URL` query string stripped, `ssl="require"`
passed as an argument, DSN never rendered): PostgreSQL 17.6, `alembic_version` `020`, RLS
enabled **and forced** on **19/19** public tables, **zero** table grants to
`anon`/`authenticated`/`PUBLIC`, no schema `USAGE`/`CREATE` for `anon`/`authenticated`, zero
sequence usage grants. `/api/docs` 404, `/api/v1/config` 401. The web root and the
`/leagues/the-coupon/leaderboard` and `/settings` deep links all return 200 with a
byte-identical SPA asset (SHA-256 `df14b4e9…`, `/assets/index-0b3QNWzJ.js`) and the committed
security/cache headers; `/sw.js` retains `cache-control: public, max-age=0, must-revalidate`
and `x-content-type-options: nosniff`. A CORS preflight from
`https://the-coupon-production.vercel.app` returns 200 with that exact
`access-control-allow-origin` and `access-control-allow-credentials: true`; a foreign origin
is refused with 400. Bounded Railway log snapshots (39 then 48 records, whole-record scans)
show the alembic no-op, `Application startup complete`, `Uvicorn running`, zero
content-classified errors or 5xx served, and zero matches across the DSN / JWT / `apiKey=` /
PEM / bearer / labelled-PIN leak patterns. The Vercel build log for the promoted deployment
is a clean `vite build` with an 81-entry PWA precache and `Deployment completed`.

Backup/restore-point identity: **none** — production has no managed backup, no PITR and no
durable dump, under the owner's 2026-07-30 deferral. Rollback reverts application
deployments only.

### Forward recovery plan — migration `021`, Batch 107

**Status: approved by the owner, 2026-09-04. Cleared to ship.**

Required by `/ship-prod` step 1.7 before `021` may be deployed. Production is at head `020`
(deployment `e95ff966-f7ee-4587-999f-5470063ef108`, `SUCCESS`, serving `9e91b604`); this
shipment moves it to `021` and carries Batch 107 — the Group L checkpoint.

**No pre-migration snapshot is needed. `021` rewrites nothing.** It is one `CREATE TABLE`
for a table that does not exist (`gameweek_completions`), plus the standard Supabase RLS
lockdown block that `003`/`004`/`009`/`011`/`018` apply to every new table. No existing table
is touched, no column is added or dropped, no row is rewritten, no value recomputed, no enum
altered. It is the same shape as `018` (Batch 99's `rate_limit_counters`) and strictly
smaller than it — one table rather than one table plus an index.

**It cannot refuse to run.** Unlike `017` there is no precondition it checks and no state of
the data that can make it fail. The only failure modes available to a bare `CREATE TABLE`
are a name collision and a missing function in a `server_default`, and neither exists here:
no migration in `001`–`020` creates a `gameweek_completions`, and `gen_random_uuid()` has
been the `_UUID_PK` default since `011` shipped on 2026-08-06 against this same PostgreSQL
17.6 instance, where it is a built-in rather than a `pgcrypto` extension.

**The rollout window is safe in both directions, which is not true of every migration here.**
The new container runs `alembic upgrade head` while the old one is still serving. The old
image never reads, writes or joins `gameweek_completions` — it does not know the table
exists — so creating it underneath a running `020` container changes nothing that container
does.

**API rollback is unavailable the moment `021` applies**, on the same terms as `012`, `013`,
`014`/`015`, `017`, `019` and `020`: every pre-`021` image ships revisions `001`–`020` only,
so started against a database stamped `021` its Alembic fails with `Can't locate revision
identified by '021'` before uvicorn is reached, the `&&` chain in `nixpacks.toml` stops, and
the healthcheck fails. **Do not attempt a Railway rollback to `e95ff966`, `7ec86030`, or
anything older after this ships.** The recorded baseline is a record, not a usable target.
Vercel rollback is unaffected.

**The block is Alembic's revision resolution and nothing else — there is no data hazard
behind it.** This is the one place `021` differs from `020`, and the difference is worth
stating because `020`'s plan had to warn the opposite way. A `020` image running against a
`021` database would find every table and column it expects, with no unknown enum value in
any row it reads; `gameweek_completions` is simply invisible to it. If a future release ever
makes pre-`021` images bootable again, running one is *correct*, not merely permitted.

Recovery once `021` *has* applied is forward-only:

1. **Deploy a corrected image at head `021` or higher.** The normal path.
2. **Disabling Batch 107's behaviour needs no migration.** The event is recorded and
   delivered entirely from the post-commit block of `routers/picks.py::submit_pick`; removing
   its `record_completion` and `announce_all_picked` calls stops both the durable write and
   the push, and leaves the table inert. The reworded pick alert
   (`services/notification_triggers.py`) and the three progress fields on the submit response
   are likewise pure application code with no schema dependency.
3. **Emptying the table is safe, and is the only data-level lever there is.**
   `DELETE FROM gameweek_completions` — globally or for one `gameweek_id` — makes those
   rounds eligible to be announced again, and that is its *entire* effect. Nothing else in
   the schema references the table: no pick, score, standing, membership or audit row points
   at it, and no query joins it. Deleting from it cannot damage game state.
   The inverse lever is equally cheap: inserting a row with `delivered_at` set suppresses an
   announcement for a round without changing anything else.
4. **Never run `alembic downgrade` against production.** This downgrade is clean in schema
   terms — it drops one table with no dependants — but it re-arms every round the product has
   already announced: with the record gone, the next pick changed on a completed round would
   send "all picks are in" a second time. The downgrade exists for local and staging.

**Post-deploy checks specific to this shipment**, beyond the standard `/health` and
`/health/ready` agreement at `021`:

1. **Confirm the table landed with its guard rails**, in the same in-container RLS session the
   shipment already runs: `gameweek_completions` present, `uq_gameweek_completions_gameweek`
   present, RLS **enabled and forced**, and zero `anon`/`authenticated`/`PUBLIC` grants. The
   table count in that check moves from 19 to 20, and a table that appears *without* forced
   RLS would mean the migration's `DO $$` lockdown block did not see the `auth` schema.
2. **Nothing web-facing consumes this yet, and that is the point of the checkpoint.**
   Batch 108 is the consumer and has not been built. The deployed bundle ignores the three
   new response fields because TypeScript interfaces are structural, so the only
   member-visible change from this shipment is the reworded pick push — which reaches phones
   on the first pick made in any league after the deploy.
3. **`alembic upgrade head` must print exactly one `Running upgrade 020 -> 021` line** in the
   bounded boot-log snapshot. More than one, or none, means the database was not where this
   plan assumes.

### 2026-09-04 — `3366b38`, Batch 107 (pick progress + the all-picked event, **migration `021`**)

Source commit `3366b38` (`3366b38f8d9efa046fdb1a4ab1c4964d1a85dacf`), on `origin/main`. The
Group L checkpoint: Batch 107 is API/data only, and Batch 108 must not reach Vercel until
this shipment serves the fields it consumes.

**Gate coverage, stated precisely because two docs commits sit between the two runs.**
`scripts/ci-local.sh` passed 11/11 against the tree at `e998541` **plus** the appended
forward-recovery-plan text — that is, a tree identical to the shipping commit except for the
one status line `3366b38` flips in this document. The GitHub `Quality` run then ran the full
CI on `3366b38` itself and concluded `success`
(`https://github.com/CraigR973/the-coupon/actions/runs/33878500523`), confirmed to **exist**
for that exact commit rather than merely not to have failed.

**Alembic revision `021`**, so preflight step 1.7 applied. The forward recovery plan above
was written first (`fbed2e5`) and approved by the owner in its own commit (`3366b38`) before
anything was deployed, matching the `017` and `020` pattern.

`railway config plan` under Node 22 returned **`0 to add, 2 to change, 0 to destroy`**,
`"destructive": false`, both changes `"kind": "resource.update"` / `"severity": "safe"`,
`declared: ["service.api"]`, `diagnostics: []` — and the change set contains no occurrence of
`variable`, `delete`, `destroy` or `remove`, so nothing was dropped. The two changes
re-assert what the running deployment already used: `build.nixpacksConfigPath`
`null → "nixpacks.toml"`, and `deploy.numReplicas` `null → 1`, `deploy.restartPolicyType`
`null → "ON_FAILURE"`, `deploy.sleepApplication` `null → false`. **Those fields read back as
`null` at the service-instance layer between applies** — a direct `serviceInstance` query
before the plan showed `numReplicas: null`, `region: null` — which is why the same safe
diff reappears each shipment; it is the dormant override layer, not what the container ran.
`railwayConfigFile` was `null` before and after.

Applied with `railway config apply --plan <pinned> --yes`, no `--confirm-destructive`, plan
file removed afterwards. The apply minted redeploy
`ea78e1e4-1c82-4988-a7d8-c9fa14cc41a9` (rebuilding the prior source `9e91b604`), polled to
`SUCCESS` **before** the source upload; `/health` stayed green at `9e91b604` / `020`
throughout, so the config layer moved without moving what was running.

`RAILWAY_GIT_COMMIT_SHA` was then stamped to `3366b38f…` with `--skip-deploys`, the worktree
re-checked clean immediately before the upload, and `railway up` ran with every selector
explicit: deployment `1e33a63b-ebb4-463d-9134-7e5e00866339`, `SUCCESS`, message
`ship production 3366b38`, `imageDigest
sha256:61d0f4dd2bfcd2c87c289978e169ca0c14de00faccace84088f4398c9ea9e888`. The
`deploymentEvents` breakdown shows `SNAPSHOT_CODE`, `BUILD_IMAGE`, `CREATE_CONTAINER`,
`HEALTHCHECK`, `CONFIGURE_NETWORK` and `DRAIN_INSTANCES` all with a real `completedAt` — a
clean promotion in about four minutes, no stall.

**Railway rollback baseline: `e95ff966-f7ee-4587-999f-5470063ef108`** — the deployment live
immediately before this shipment, serving `9e91b604` at head `020`. It is recorded as the
baseline and **is not a usable target**: this shipment migrates, so a pre-`021` image cannot
resolve revision `021` and fails before uvicorn. Recovery is forward-only per the plan above,
which is unusually cheap here — the table has no dependants and disabling Batch 107 needs no
migration.

Section 4 was skipped by design. Vercel's GitHub integration had already built `3366b38f` as
`dpl_BupSmeQJQK8jvg5dqTcsx6mDoumL` (immutable
`the-coupon-production-315uaf5db-craigr973s-projects.vercel.app`), and it already held the
stable alias `https://the-coupon-production.vercel.app` — confirmed by reading
`githubCommitSha` from the Vercel API and by `vercel inspect` on the alias, not inferred from
timing. Its predecessor `dpl_9jAgm3TsMHo8QAKBxoWZ3PShjZVg` (`fbed2e52`) is the **Vercel
rollback baseline**.

Post-deploy verification: `/health` reports sha `3366b38f…` and migration `021`,
`/health/ready` agrees at `021` with `db: ok` — the two agreeing is what says the boot-time
`alembic upgrade head` completed. The deployment manifest confirms `numReplicas: 1`,
`multiRegionConfig: { "europe-west4-drams3a": { numReplicas: 1 } }`, `sleepApplication:
false`, `ipv6EgressEnabled: true`, `healthcheckPath: /api/v1/health/ready` at `300`,
`restartPolicyType: ON_FAILURE` ×3, `limitOverride.containers` `cpu 0.25` /
`memoryBytes 500000000`, `builder: NIXPACKS` with `nixpacksConfigPath: /nixpacks.toml`.

An in-container recheck over an asyncpg session (`/opt/venv/bin/python` via `railway ssh`,
`DATABASE_URL` query string stripped, `ssl="require"` passed as an argument, DSN never
rendered): PostgreSQL 17.6, `alembic_version` `021`, RLS enabled **and forced** on **20/20**
public tables — **19/19 last shipment; the new table is the twentieth and it arrived
locked**, which is the migration's `DO $$` Supabase block having seen the `auth` schema.
`gameweek_completions` present with `uq_gameweek_completions_gameweek` and **0 rows**;
**zero** table grants to `anon`/`authenticated`/`PUBLIC`, no schema `USAGE`/`CREATE` for
either role, zero sequence usage grants. `/api/docs` 404, `/openapi.json` 404,
`/api/v1/config` 401.

The web root and the `/leagues/the-coupon/leaderboard` and `/settings` deep links all return
200 with a byte-identical SPA asset (SHA-256 `462d65b0…`), bundle
`/assets/index-Bc_jdQY6.js` served `public, max-age=31536000, immutable`, and all three
committed global headers present (`x-content-type-options`, `referrer-policy`,
`permissions-policy`) alongside HSTS; `/sw.js` retains `public, max-age=0, must-revalidate`
and `nosniff`. A CORS preflight from `https://the-coupon-production.vercel.app` returns 200
with that exact `access-control-allow-origin` and `access-control-allow-credentials: true`;
a foreign origin is refused with 400.

Bounded Railway log snapshots (40 then 47 records, whole-record scans, structured events read
from the record rather than the rendered message) show **exactly one**
`Running upgrade 020 -> 021` line, `api starting`, `Scheduler started`,
`Application startup complete`, `Uvicorn running`, zero 5xx served, zero error-classified
lines, and **zero** matches across the DSN, Supabase-ref, JWT, PEM, `api_key=`, bearer and
labelled-PIN patterns. Batch 93's boot task still logs `rename notice undelivered, will retry
next boot` followed by `rename notices processed`, which remains the **correct** result for
members with no active push subscription. The Vercel build log for the promoted deployment is
a clean `vite build` with a 79-entry PWA precache and `Deployment completed`.

**What could not be probed from outside, stated rather than glossed.** The new pick-response
fields (`picked_count`, `member_count`, `all_picked`) and the reworded push copy sit behind an
authenticated mutation that spends the odds provider's rate-limited quota, and production
serves no OpenAPI document, so neither was exercised against production. They are attested by
the gate and by `/health` reporting the shipped image head, not by a live probe — and
deliberately so: submitting a pick against production is a destructive probe this workflow
forbids.

**Member-visible effect.** The reworded pick alert reaches phones on the first pick made in
any league after this deploy; the all-picked event fires the first time a league's round
fills. Batch 108 is not built, so nothing in the deployed bundle reads the new response
fields yet — TypeScript interfaces are structural, so the extra keys are simply ignored.

Backup/restore-point identity: **none** — production has no managed backup, no PITR and no
durable dump, under the owner's 2026-07-30 deferral. Rollback reverts application deployments
only, and for this shipment the API half of that is unavailable.

`scripts/check-deploy-drift.sh` reports **in sync**: `origin/main` and the deployed API both
at `3366b38f`, migration `021`.

### Forward recovery plan — migration `022`, Batch 110

**Status: written 2026-09-04, awaiting owner approval. Not cleared to ship.**

Required by `/ship-prod` step 1.7 before `022` may be deployed. Production is measured at
head `021` serving `3366b38f`; this shipment moves it to `022` and carries Batch 110 — the
Group M checkpoint.

**This one alters an existing table, which `021` did not.** `022` is three statements
against `matches`: `ADD COLUMN state VARCHAR(16) NOT NULL DEFAULT 'scheduled'`, one
`UPDATE ... SET state = 'finished' WHERE finished`, and one `CREATE INDEX`. That is a
larger claim on a live table than any migration since `017`, so the size of it was measured
rather than assumed, read-only from the running container on 2026-09-04:

| measured | value |
| --- | --- |
| `alembic_version` | `021` |
| PostgreSQL | 17.6 |
| `matches` | **755 rows, all `finished`**, 464 kB including indexes |
| `matches` where `NOT finished` | 0 |
| pooled competitions (`fixtures`) | 23 |
| whole database | 13 MB |

**Nothing here can be slow, and nothing here can fail.** On PostgreSQL 11 and above an
`ADD COLUMN` with a *constant* default is metadata-only — the row values are never
rewritten, so table size is irrelevant to it and the `ACCESS EXCLUSIVE` lock is held for
the length of a catalogue update. The `UPDATE` rewrites 755 rows and the `CREATE INDEX`
builds over the same 755; both are milliseconds against a 464 kB table, inside a
`healthcheckTimeout` of 300 seconds. There is no type change, no constraint that existing
data could violate, and no `NOT NULL` added without a default — which is the only shape of
`ADD COLUMN` that can refuse to run.

**The rollout window is safe, and the server default is what makes it safe.** The new
container runs `alembic upgrade head` while the `021` container is still serving. That
older image has no `state` in its `Match` model: SQLAlchemy emits explicit column lists, so
its `SELECT`s cannot see a column added underneath them, and its `INSERT`s omit `state`
entirely — which succeeds only because the column carries `DEFAULT 'scheduled'`. A
`NOT NULL` column without one would have made every write from the still-serving old image
fail for the length of the rollout. The default is load-bearing, not decoration.

**API rollback is unavailable the moment `022` applies**, on the same terms as `012`
onwards: every pre-`022` image ships revisions `001`–`021` only, so against a database
stamped `022` its Alembic fails with `Can't locate revision identified by '022'` before
uvicorn is reached, the `&&` chain in `nixpacks.toml` stops, and the healthcheck fails.
**Do not attempt a Railway rollback to `3366b38f` or anything older after this ships.** The
recorded baseline is a record, not a usable target. Vercel rollback is unaffected.

**Unlike `021`, there is a real data hazard behind that block, and it is worth naming.**
`021` created a table the old image could not see, so an old image on a new database was
merely permitted. Here it would be actively wrong: a `021` image writes `finished` and knows
nothing of `state`, so every match it transitioned — a fixture kicking off, a match reaching
full time — would keep whatever `state` it was last written with while `finished` moved
underneath it. The column would drift silently and only a full re-sweep would repair it. If
a future release ever makes pre-`022` images bootable against this database, running one is
**not** safe, and this paragraph is the reason.

**One backfill fidelity caveat, currently moot.** The `UPDATE` maps the only two states the
old column could express: `finished` becomes `finished`, everything else becomes
`scheduled`. A match *in play* at the instant the migration runs would therefore be recorded
as `scheduled` rather than `live`. It self-corrects on the next live-scores sweep, and today
the measured count of unfinished rows is 0 — but the shipment should still avoid a Saturday
afternoon, which is the general rule here anyway.

Recovery once `022` *has* applied is forward-only:

1. **Deploy a corrected image at head `022` or higher.** The normal path.
2. **Disabling Batch 110's behaviour needs no migration.** Two independent levers, either
   safe alone: delete the `teams/{team_id}/season` route from `routers/football.py`, and/or
   revert `sync_competition` to call `fetch_results` with its window instead of
   `fetch_season_matches`. The column and index go inert; nothing else reads `state`.
3. **`DELETE FROM matches WHERE NOT finished` returns the table to its pre-Batch-110
   contents, and that is its entire effect.** Nothing in the schema references `matches` —
   there is no foreign key pointing at it anywhere — and every read older than this batch
   (`recent_results`, `team_form`, `fixture_context`, settled scorelines) already gates on
   `finished`. It also removes any in-play row, which the next live-scores sweep rewrites
   within the hour. It cannot damage a pick, a score or a standing.
4. **Never run `alembic downgrade` against production.** This downgrade *is* schema-clean —
   one index and one column, no dependants — and unlike most here it would even restore
   pre-`022` bootability. It is still forbidden: the running image is at `022` and would
   re-apply it on the next boot, and the information it discards (which unplayed matches
   were postponed rather than cancelled) is recoverable only by a full provider sweep.

**What this shipment does to the size of things**, since Supabase production is a Free plan
whose egress quota has a standing unattributed consumer (FEAT-A09, which has already caused
one 402):

* The immediate step is small. The daily sweep's window was already
  `football_results_lookback_days = 30`, and the 2026-27 season is about a month old, so
  "the last 30 days" and "the whole season" are currently almost the same set of matches.
* The growth is gradual and bounded by the season. At 23 pooled competitions the table
  should reach roughly 10,000–14,000 rows by May — about 9 MB at the measured 615 bytes a
  row, against a 13 MB database today. **Storage is not the concern.**
* The recurring cost is the sweep's own read. `sync_results` selects existing rows for every
  match id it is about to write, so that read grows with the season: a few hundred kilobytes
  a day now, of the order of 3–4 MB a day by May. Worth watching against the quota rather
  than worth blocking on, and lever 2 above reverses it without a migration.

**Post-deploy checks specific to this shipment**, beyond the standard `/health` and
`/health/ready` agreement at `022`:

1. **`alembic upgrade head` must print exactly one `Running upgrade 021 -> 022` line** in
   the bounded boot-log snapshot. More than one, or none, means the database was not where
   this plan assumes.
2. **Confirm the column and index landed, and that the table's guard rails did not move.**
   In the same in-container session the shipment already runs: `matches.state` present as
   `character varying(16)`, `NOT NULL`, default `'scheduled'`; index
   `ix_matches_competition_season_state` present; **no row with a null or empty `state`**;
   and `matches` still RLS **enabled and forced** with zero `anon`/`authenticated`/`PUBLIC`
   grants. The table count does not change — `022` creates no table — so an unchanged count
   is the expected result here, not a warning sign.
3. **Confirm the backfill agrees with the old column**: zero rows where
   `finished AND state <> 'finished'`. Against the measured 755-row table every row should
   read `finished` immediately after the migration, before any sweep has run.
4. **Exercise the new route once**, signed in: a 200 with a `matches` array for a stored
   club, and a 404 for a random UUID. It is the only new surface, and nothing web-facing
   consumes it yet — Batch 111 is the consumer and has not been built, which is the whole
   point of stopping the group here.

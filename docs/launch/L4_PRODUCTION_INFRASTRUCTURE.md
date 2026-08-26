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

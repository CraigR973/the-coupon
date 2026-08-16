# L4 — production infrastructure record

Started: 2026-07-30

This is the non-secret implementation record for L4. It does not mark the
phase complete. Only `/launch-closeout L4` may close the gate.

> **Reading this record.** Everything below the budget section is dated
> evidence — it describes what was true when the gate was verified
> (2026-07-31 to 2026-08-03), not what is true now. In particular, statements
> that migration `004` is "the repository's sole head" were accurate then; the
> head is now `011`. For current deployment IDs, migration head, and rollback
> baselines, read **Shipment history** near the end and treat it as
> authoritative wherever it disagrees with the dated sections.

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

The 2026-08-15 shipment closed a nine-day reporting gap rather than a drift.
Investigation that morning confirmed against Railway's GraphQL API that
`7a5862cb` was still current and carried `aae3b51e`, so the API had never fallen
behind; `/health` reported `sha: unknown` only because that image predated the
`/ship-prod` step that stamps `RAILWAY_GIT_COMMIT_SHA`. A blank `sha` is a
reporting gap, not evidence of drift — but it is indistinguishable from one from
the outside, which is why `/health` now also reports the migration head bundled
in the image. Since this shipment `/health` reports the exact commit and
`check-deploy-drift.sh` answers from tier 1: `in sync`, exit 0.

The Vercel deployment above was **not** minted by `/ship-prod`. It is the
GitHub-linked auto-deploy of the same push, which already held the stable alias
by the time the API shipped; section 4 was skipped by design.

### Current rollback baselines

Updated after the 2026-08-16 shipment of `13560cdb` (migration `012`).

| Stack | Roll back to |
| --- | --- |
| Railway `api` | **Nothing. There is no API rollback at head `012`.** See below — this is not a caveat, it is the state. |
| Vercel web | `dpl_3eNqpZKAFZkAG6DT1HAUiU8aJm8j` (`e43de93`), the immediate predecessor of the live `dpl_2oJN39b62QTWu1tLkctde33yasze` |

**The API rollback that existed at head `011` is gone, exactly as predicted.**
The previous version of this section recorded `7a5862cb` as the first
schema-compatible predecessor, and noted that it held "only while the head stays
`011`: the next shipment that adds a migration returns the API to
fix-forward-only". Migration `012` is that shipment.

The reason is the boot sequence, not the schema. `nixpacks.toml` starts with
`alembic upgrade head && uvicorn ...`, and every pre-`012` image ships migration
scripts `001`–`011` only. Started against a database stamped `012`, such an image
cannot resolve the revision at all — it fails with `Can't locate revision
identified by '012'`, the `&&` chain stops, uvicorn never starts, and the
healthcheck fails. **This holds regardless of what is in the tables**, so it is
not something a data fix can unlock. Do not attempt a Railway rollback to
`df6626e0` or anything older; it will fail its healthcheck rather than serve.

Recovery is forward-only, per the approved plan for `012` below: clear the
opt-in and remap any `scheduled` rounds without deploying anything, or ship a
corrected image at head `012` or higher.

An API rollback target will exist again once a *second* deployment sits at head
`012`, at which point `f54fa403` becomes the baseline. Until then this row stays
empty. Note also that a `REMOVED` Railway deployment may have had its image
pruned, and `canRedeploy: true` is reported even for deployments that could not
possibly restore — it is not evidence of anything.

**Vercel rollback is unaffected and remains available.** The web app degrades
independently of the API, and the API is now ahead of every web deployment, so
an older bundle still finds every field and endpoint it expects. Vercel marks
only the two most recent production deployments `isRollbackCandidate: true`, so
the practical target is the immediate predecessor named above. Verified
2026-08-16.

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

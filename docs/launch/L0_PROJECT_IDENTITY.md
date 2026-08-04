# L0 — project identity and owner decisions

Recorded: 2026-07-26

This is the source of record for launch target selection. The owner's
instruction to implement L0 accepts the default MVP scope in
`docs/LAUNCH_PLAN.md`. It does not authorize a domain purchase, a paid project,
a deployment, a database mutation, a real Betfair login, or member invitations.
Those actions remain limited to their later launch phases.

Owner decisions recorded on 2026-07-26:

- administrator display name: `Craig`;
- initial roster: 15 profiles and 15 league memberships, including Craig;
- Sentry: omitted from the MVP.
- repository visibility: public, explicitly selected by the owner so GitHub
  Actions can use public-repository runner allocation.

## Post-launch environment lifecycle amendment

Owner decision recorded on 2026-07-29:

- retain a complete, isolated staging stack through L3, L4, and the first live
  Saturday in L5;
- after that gate is green, keep production as the only always-on stack and
  operate staging as dormant/on-demand;
- allow the synthetic-only Supabase Free staging project to pause, use
  Railway Serverless or stop the staging API between rehearsals, and use Vercel
  Preview deployments for routine frontend review;
- reactivate the full staging stack before database migrations,
  authentication, scheduler, push, Betfair integration, restore, or similarly
  risky changes; and
- retain staging/production isolation. Dormancy does not authorize deleting a
  recorded target, reusing production data, or running destructive verification
  against production.

The production API remains exactly one always-on Railway replica because the
embedded scheduler must continue to execute. A dormant staging API is not
expected to run scheduled jobs. Before a staging rehearsal, resume or recreate
the database, apply migrations and synthetic seed data, wake exactly one API
replica, deploy the matching frontend, and recheck readiness, CORS, and SPA deep
links.

## Supabase plan and project-count amendment

Owner decision recorded on 2026-07-30, superseding the L4 working assumption of
a Supabase Pro organization:

- keep `CraigR973's Org` on the Free plan; the Coupon budget for Supabase is
  USD 0;
- run exactly one active Coupon Supabase project, which is production; and
- free the required Free-plan slot by pausing `the-coupon-staging` rather than
  by pausing or deleting any non-Coupon project.

The withdrawn Pro estimate was also wrong on its own terms. Supabase sets the
plan per organization, so upgrading would have applied to every project in
`CraigR973's Org`, not to two Coupon projects in isolation, costing about
USD 45/month rather than the USD 35 previously recorded.

This brings forward the dormant-staging lifecycle that the 2026-07-29
amendment scheduled for after the first live Saturday. The consequence is
accepted knowingly: no staging database rehearsal is available during L4 and
L5. L3 is already closed and green, the paused project stays restorable within
the platform's 90-day window, and the Railway and Vercel staging targets are
unaffected. Reactivating staging later requires resuming the project inside
that window or rebuilding it from migrations and synthetic seed data, and it
must not displace the active production project.

Free-plan consequences accepted for production: no managed daily backups and
no PITR add-on, a 500 MB database ceiling, and 5 GB monthly egress. Automatic
pausing is not a material risk for production because the always-on Railway
replica warms the connection every ten minutes and dumps daily, which exceeds
Supabase's stated activity bar.

## Backup deferral

Owner decision recorded on 2026-07-30: **the launch ships with no database
backup**, deferring `docs/LAUNCH_PLAN.md`'s durable-backup blocking finding to
post-launch. The owner was shown the risk, asked again, and reaffirmed, citing
a previous World Cup predictor run without backups.

Recorded so the record is honest rather than silent:

- Production has no managed backup, no PITR, and no durable copy of the
  nightly logical dump. The dump still runs at 03:00 UTC and still logs a
  successful backup, but it writes to Railway's ephemeral filesystem and is
  discarded on every deploy. Nobody should later read that log line as
  evidence a backup exists.
- `picks` is the only irreplaceable table. `odds_at_pick` is frozen at pick
  time and `points_awarded`/`status` are written at settlement; nothing else
  can reconstruct them. Profiles and the league re-bootstrap from the roster
  file, fixtures re-fetch from Betfair, and standings recompute from picks.
  `audit_log` is not a second copy: it records only league membership changes
  and backup failures, and it lives in the same database.
- Routine operation does not endanger picks. `sync_slate` upserts fixtures and
  never deletes, so the weekly refresh cannot cascade picks away.
- The exposure is a bad migration, a mistaken administrative write, or
  platform-side loss. Migration risk is elevated because `nixpacks.toml` runs
  `alembic upgrade head` on every boot, so migrations reach production with no
  human gate and, on Free, no undo.
- Consequently, deployment rollback must never assume a recoverable database.

## MVP scope

The launch keeps the seven defaults in `docs/LAUNCH_PLAN.md`:

1. Supabase is PostgreSQL only; incomplete avatar upload and dead Supabase
   application configuration are removed in L1.
2. Push remains, with the web settings aligned to global mute and quiet hours.
3. Web and API use separate, explicit HTTPS origins.
4. Passwordless device activation is removed; display name plus PIN remains.
5. L1 adds an admin-operated one-time PIN reset that does not log secrets.
6. The scheduler remains embedded in exactly one always-on Railway replica,
   with settlement retries added in L1.
7. MVP monitoring uses Railway and Vercel platform logs; Sentry is omitted.

## Ownership and fresh target names

Ambient authentication was used only to identify owner-controlled accounts.
No existing project was selected as a Coupon target.

| System | Selected owner | Fresh Coupon targets | Provisioning phase |
| --- | --- | --- | --- |
| GitHub | Personal account `CraigR973` | Public repository `CraigR973/the-coupon` | Created in L0 |
| Supabase | `CraigR973's Org` (`eufhjqkyoiuzfwuptlyn`) | `the-coupon-staging`, `the-coupon-production` | L2, L4 |
| Railway | `Craig Robinson's Projects` (`518ea7c5-7ee6-464b-bcf0-befed3153c1f`) | Projects `the-coupon-staging`, `the-coupon-production`; service `api` in each | L2, L4 |
| Vercel | `craigr973's projects` (`team_MVQMOaFtYHlwO5QVzSOZQ0Ud`) | Projects `the-coupon-staging`, `the-coupon-production` | L2, L4 |
| Betfair | Owner account only; agents may not log in | Delayed/read-only app identity for production only; staging uses `FakeBetfair` | Owner action in L4 |

The following discovered resources are explicitly excluded:

- Supabase refs `lesscrmlfijiokureomm` (`wc2026-staging`),
  `kznxjyaanotrejcevngy` (`wc2026-predictor`), and
  `pzqmswvozjnkxbqqowuj` (`CraigR973's Project`).
- Every existing Railway project, including `garmin-coach` and
  `wc2026-api-prod`.
- Every existing Vercel project, including Garmin and WC2026 projects.

Fresh Supabase and hosting project IDs must be appended here when L2 and L4
create them. Names alone never authorize a connector or CLI target.

L2 staging targets created so far:

- Supabase project `the-coupon-staging`:
  `gegcnhoeudpkcoxqcebe` in `eufhjqkyoiuzfwuptlyn`.
- Railway project `the-coupon-staging`:
  `cc2fc994-87c3-4e2e-8d9b-5bcafa496350`; environment
  `333ffc77-ad0d-43af-8436-4865fb9c2946`; service `api`
  (`535e77d7-f8a2-4fd4-85a3-e8cb0ada7fd8`).
- Vercel project `the-coupon-staging`:
  `prj_r9VsE4xnCj53S3OiOUH7GSzQsn2c` in
  `team_MVQMOaFtYHlwO5QVzSOZQ0Ud`.

L4 production targets created so far:

- Supabase project `the-coupon-production`: `pugujiiojitstkilphrz`, London
  (`eu-west-2`), Free plan, PostgreSQL 17.6, created 2026-07-31. It is the
  only active Coupon Supabase project and is never attached to MCP.
- Railway project `the-coupon-production`:
  `e030ebe3-e7fc-43c9-9478-4e80cafaa126`; environment `production`
  (`8f18cb49-5137-4557-900a-031bcab4ac38`); service `api`
  (`d59f4f17-3e7d-4b3b-bf40-30620150fa2f`).
- Vercel project `the-coupon-production`:
  `prj_3h3OSNFDoPAySqTa9nVswUrMs0jJ` in
  `team_MVQMOaFtYHlwO5QVzSOZQ0Ud`.

The database is migrated and locked down. The two hosting targets are reserved
but not deployed. Neither creation nor migration satisfies the production gate.

## Repository and integration

- `origin` is `https://github.com/CraigR973/the-coupon.git`.
- The owner explicitly selected public visibility on 2026-07-26 after private
  GitHub Actions jobs were blocked by account billing limits.
- L0 verification must not push.
- All launch phases integrate through pull requests and the required
  `Quality / backend` and `Quality / frontend` checks. A phase is not merged
  while either check is missing or failing.
- L0 close-out bootstrapped the unchanged pre-L0 local `main` to the verified
  repository, then pushes the L0 branch and follows the same pull-request path.
  No implementation is pushed directly to `main`.
- Close-out bookkeeping is committed on the phase branch before its pull
  request, as defined by the canonical `/launch-closeout` workflow. After merge,
  local `main` is fast-forwarded to the remote result.
- Force pushes, direct implementation pushes to `main`, and required-check
  bypasses are prohibited.

## Hostnames

The MVP uses only the no-cost hostnames assigned by Vercel and Railway. No
custom domain will be purchased or configured.

| Environment | Web | API |
| --- | --- | --- |
| Staging | `https://the-coupon-staging.vercel.app` | `https://api-production-0641.up.railway.app` |
| Production | Intended stable alias `https://the-coupon-production.vercel.app`; confirm after the first production deployment | `https://api-production-109b1.up.railway.app` |

L2 and L4 must record the exact assigned HTTPS hostnames and project/service
IDs immediately after provisioning. The project and service names must not be
changed afterward because those platform hostnames form the MVP's stable public
origin contract. `VITE_API_URL` and `FRONTEND_ORIGIN` must use those exact,
environment-specific origins.

## Regions and time

- Product scheduling and lock rules: `Europe/London`.
- Supabase staging and production databases: `eu-west-2` (London).
- Railway staging and production APIs: one replica in EU West Metal,
  `europe-west4-drams3a` (Amsterdam).
- Vercel web assets: global CDN. The current static Vite frontend has no
  server-function region to configure.

Staging and production use the same regions but separate projects, credentials,
databases, deployment aliases, and domains.

## Budget controls

Coupon-specific recurring infrastructure must remain at or below USD 50 per
month unless the owner explicitly changes this record.

- Supabase: use Pro with Micro compute, keep its spend cap enabled, and stop
  before provisioning if the two Coupon projects would take projected
  Coupon-specific recurring spend above USD 35 per month.
- Railway: use Hobby, set a USD 10 compute alert and USD 15 compute hard limit,
  and disable Railway Agent spending for the Coupon projects.
- Vercel: use its no-cost personal tier for the MVP. Stop if a required setting
  needs a paid plan.
- Sentry: omitted; approved spend is USD 0.
- Domain and DNS budget: USD 0; use platform-assigned hostnames.
- Every provisioning phase must show the current checkout or cost estimate to
  the owner before creating a paid resource. No existing unrelated project's
  budget or quota is treated as Coupon capacity.

L2 staging exceptions recorded on 2026-07-27:

- After pausing an unrelated Supabase project, the owner directed L2 to use the
  newly available Free-plan slot. Staging therefore costs USD 0, may be paused
  by Supabase after inactivity, and has no managed daily backups. It contains
  synthetic data only; L3 must complete a manual export/restore rehearsal.
  This does not waive the production backup and paid-plan decision in L4.
- Railway compute limits are workspace-wide and the selected workspace also
  hosts excluded projects. L2 did not apply a shared hard shutdown limit.
  Instead, the staging `api` replica is capped at 0.25 vCPU and 500 MB, which
  bounds its maximum CPU-plus-memory allocation to about USD 10/month at
  current list pricing while leaving unrelated workloads untouched.

The steady-state budget after the first-Saturday gate assumes that only
production is deliberately kept warm. Staging retains its isolated target
identity but is not kept active solely to prevent Supabase pausing or Railway
sleep. Before dormancy, capture a current logical export. If target continuity
matters, resume a paused Supabase Free project within the platform's current
90-day restore window; otherwise rebuild it from migrations, the logical
export where needed, and synthetic seed data.

## Supabase connector boundary

The former `.codex/config.toml` ref `lesscrmlfijiokureomm` is rejected because
account-level metadata identifies it as `wc2026-staging`. The repository MCP
URL is now scoped read-only to staging ref `gegcnhoeudpkcoxqcebe`, with only
database, debugging, development, and documentation feature groups enabled.
Production must never be connected to an agent MCP server.

## Initial roster handling

Real display names, PINs, reset tokens, phone numbers, and invitation details
must not be committed. The owner supplies the reviewed roster out of band in
`.launch-private/roster.json`, which is ignored by Git. L1 provides the
idempotent JSON bootstrap command; L4 will record only the expected 15 profiles
and 15 league memberships as verification evidence.

The administrator display name is `Craig`. The other 14 display names remain
owner-held and will be supplied through the ignored roster file when L4 is
ready.

No initial PINs are needed in L0. They will be generated or entered at
bootstrap and distributed by the owner outside logs, Git, and chat.

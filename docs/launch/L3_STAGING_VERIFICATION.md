# L3 — staging verification record

Started: 2026-07-29

This is the non-secret implementation and evidence record for L3. It does not
mark the phase complete. Only `/launch-closeout L3` may close the gate after
`/launch-verify L3` returns GREEN.

## Exact targets

| Component | Exact staging target |
| --- | --- |
| Supabase | `the-coupon-staging` (`gegcnhoeudpkcoxqcebe`) |
| Railway project | `the-coupon-staging` (`cc2fc994-87c3-4e2e-8d9b-5bcafa496350`) |
| Railway environment | `production` (`333ffc77-ad0d-43af-8436-4865fb9c2946`) in the dedicated staging project |
| Railway service | `api` (`535e77d7-f8a2-4fd4-85a3-e8cb0ada7fd8`) |
| Railway deployment | `6b8ca99f-4423-48f3-a6ed-73d588ad8b95` (`SUCCESS`) |
| Railway deployment instance | `89f51f6b-fb26-4d20-8b4f-1b565aa3e59c` |
| API origin | `https://api-production-0641.up.railway.app` |
| Vercel team | `team_MVQMOaFtYHlwO5QVzSOZQ0Ud` |
| Vercel project | `the-coupon-staging` (`prj_r9VsE4xnCj53S3OiOUH7GSzQsn2c`) |
| Vercel deployment | `dpl_FX53BDv6KVPVzEwcknPsknATqSaA` (`READY`, created `2026-07-29T08:21:37Z`) |
| Web origin | `https://the-coupon-staging.vercel.app` |
| Source commit under test | `4d5d29da71df639daff547b04c57a3f44f8b06f0` |

The Vercel deployment is newer than the L2 rollback baseline because the
connected `main` branch deployed after L2 close-out. No deployment or rollback
was performed during L3 implementation; those actions require
`/ship-staging`.

## Implemented verification support and fixes

- Added an explicit HTTPS-only staging Playwright configuration and a
  deterministic five-part browser flow covering durable lockout, deep links,
  membership administration, unique picks, lock, settlement retry, standings,
  combined coupon, and service-worker update behavior.
- Added a guarded staging lifecycle control that runs the real scheduler
  functions with canned `FakeBetfair` markets and refuses production/live
  modes.
- Corrected the web membership contract from the nonexistent
  `player_id`/`league_display_name` fields to the API's `id`/`display_name`
  response. A focused component test now proves that admin actions use the API
  member ID.
- Removed the leader display name from settlement logs while retaining
  non-personal outcome evidence.
- Corrected `pg_dump` TLS URL normalization, IPv6 DSNs, and portable
  ownership/privilege flags.
- Changed the Railway build from an unspecified PostgreSQL client to
  `postgresql_17`, matching staging PostgreSQL 17.
- Added guarded logical export and disposable pip-`pgserver` restore tools for
  the Free-plan synthetic staging database.
- Updated the scheduler and backup/restore runbooks with the L3 procedures and
  safety boundaries.

These changes are local on `chore/launch-l3-staging-verification` until the
reviewed close-out and shipment workflows are invoked.

## CI and local verification

- GitHub Actions run
  `30435196533`, attempt 2, completed successfully at
  `2026-07-29T12:46:47Z` for the deployed source commit. Backend, frontend,
  deployment configuration, and production-bundle jobs were all green.
- Local backend verification passed Ruff check, Ruff format verification,
  strict mypy, a clean migration through revision `004`, and all 161 tests
  against a fresh pip-`pgserver` database.
- Local frontend verification passed lint with the existing warnings,
  typecheck, all 160 tests including the new focused membership-contract test,
  and a production build.
- The local production bundle passed the SPA deep-link Playwright smoke.
- The staging Playwright configuration discovers exactly five tests and
  refuses missing or non-HTTPS staging origins.
- The three L3 operator scripts pass Ruff and bytecode compilation.

Branch CI cannot run until the implementation is committed and pushed by the
explicit close-out workflow.

## Production-bundle staging browser story

Only generated staging profiles and safe canned odds were used. Credentials
were held in a mode-`0600` temporary file and were not printed.

| Story | Evidence |
| --- | --- |
| Durable PIN lockout | Five invalid attempts returned `401`; after restarting the exact single Railway replica, the correct PIN still returned `423`. |
| SPA deep links | Direct navigation and refresh of `/settings` retained the SPA route and redirected unauthenticated access to `/login`; `/forgot-pin` rendered normally. |
| League membership | The API returned all 15 members with IDs; promote and demote each returned `204` and restored the original role. |
| Unique picks | The first player claimed the canned Arsenal selection; a second player saw it disabled as taken and claimed the canned Forfar Athletic selection. |
| Lock | The real lock scheduler function ran once and the browser displayed the locked state with selections disabled. |
| Settlement retry | The first run with open markets resolved zero picks; the second run with canned closed markets resolved both picks. |
| Standings | The settled table showed the expected 24 and 19 point totals. |
| Combined coupon | The settled two-fold showed combined odds `4.56` and both legs won. |
| PWA update | The active service worker completed `update()`; `/sw.js` returned `200` with `max-age=0`. |

The membership API behavior passed, but visual inspection of
`members-admin.png` confirms that the currently deployed web bundle does not
show the admin controls. The local contract fix and regression test address
this finding. The browser membership check must be rerun against the shipped
bundle.

### Screenshot evidence

Screenshots are stored locally under
`artifacts/launch-l3/20260729-staging/`. They contain synthetic display names
only and remain ignored by Git.

| UTC timestamp | File | SHA-256 |
| --- | --- | --- |
| `2026-07-29T12:59:27Z` | `members-admin.png` | `05eb465ff34888c99ec65a7cdc106156301d38c6fcaa5bdd713305a930a514e9` |
| `2026-07-29T12:59:36Z` | `picks-open.png` | `dd23370e99f6b93311deb676f8b42284077c6018f956655991a9abf5e7c383c8` |
| `2026-07-29T13:00:21Z` | `picks-locked.png` | `29111765e80be9d8a0cd3cdca8041d17d0d86376fc8e8e476ef620bddb9f81bf` |
| `2026-07-29T13:01:23Z` | `standings-settled.png` | `74864568535028577ae0bbac93b9f5c4757b40b8f8dda942dc9a82cd08dd9695` |
| `2026-07-29T13:01:24Z` | `combined-coupon-settled.png` | `f382c5ac8478b719ff845719e871691657760355ae4606a17c6ca45081ac3022` |

## Scheduler evidence

Railway deployment metadata confirms one always-on API replica in
`europe-west4-drams3a`, with sleep disabled.

| Job | L3 result |
| --- | --- |
| `refresh_slate` | One successful manual execution at `2026-07-29T13:19:27Z`; the existing gameweek was refreshed idempotently. |
| `pick_reminders` | One successful manual execution at `2026-07-29T13:19:39Z`; it correctly found no open gameweek after settlement. |
| `lock_gameweeks` | One successful execution through the guarded lifecycle control; one gameweek locked. |
| `settle_gameweeks` | One initial execution left two picks pending, followed by one intentional retry that resolved both and settled the gameweek. |
| `daily_backup` | Not green on the deployed revision. Historical scheduled runs failed because the asyncpg `ssl` query parameter was passed to libpq and the image contained PostgreSQL 16 `pg_dump` against PostgreSQL 17 staging. |

Two direct Railway SSH attempts at `refresh_slate` exited non-zero before a
database operation because a direct SSH child does not inherit the Nix loader
path used by PID 1. A subsequent service-runtime invocation supplied that path
and produced the single successful execution recorded above. The in-process
API remained ready throughout.

The backup defects are fixed locally, but a successful deployed backup
execution is still required after `/ship-staging`.

## Log review and health

At the end of the run:

- API liveness returned HTTP `200` with status `ok`.
- Database readiness returned HTTP `200` with status `ready` and database
  status `ok`.
- The API SHA field is `unknown` on the current CLI-uploaded Railway
  deployment; deployment IDs and the inspected Vercel source commit are the
  release identifiers for this run.
- A bounded four-hour Railway application-log scan inspected 322 records.
  Exact generated PIN values, synthetic profile names, bearer values, JWT
  shapes, PostgreSQL URLs, private-key headers, and secret assignments each
  had zero matches.
- The static Vercel deployment produced no runtime records in the same
  four-hour window and no runtime errors in the preceding seven-day check.

The local settlement-log change must be shipped before another in-process
settlement run so future logs cannot include the leader display name.

## Backup and disposable restore evidence

The guarded staging logical export completed at `2026-07-29T13:03:46Z`.

- SHA-256:
  `0ca4aff8b720a891ca3f80a4c07e6fb40b35a59e4114af5f214148459d9f7ed7`
- Migration revision: `004`
- Row counts:
  `audit_log=8`, `fixtures=2`, `gameweeks=1`, `invites=0`,
  `league_join_requests=0`, `league_memberships=15`, `leagues=1`,
  `notification_preferences=0`, `picks=2`, `profiles=15`,
  `push_subscriptions=0`, `refresh_tokens=13`

The export restored into a fresh migrated pip-`pgserver` database. Every table
count matched, `/api/v1/health/ready` returned `200`/`ready`, and the
disposable database was deleted automatically. After the final repeat, the
temporary credential and export directory was deleted without using Trash; it
is not recoverable through the normal desktop recovery path.

## Remaining gate items

L3 is **BLOCKED**, not failed:

1. A supported real phone is required for owner-observed push
   subscribe/send/unsubscribe. Staging currently has zero push subscriptions.
2. The current workflows need an owner decision before shipment. The fixes
   cannot reach the clean `main` checkout required by `/ship-staging` because
   `/launch-closeout L3` correctly refuses to commit a BLOCKED phase. The owner
   must explicitly authorize a narrow remediation commit/PR exception or amend
   the workflow before `/ship-staging`.
3. After that reviewed shipment, rerun the membership UI story, the scheduled
   backup, readiness, and the bounded log scan.
4. The same shipment must exercise and record rollback of both exact staging
   targets, then restore the reviewed forward deployments. L3 implementation
   does not authorize deployment or rollback without `/ship-staging`.
5. After those items pass, run `/launch-verify L3`. A GREEN result still waits
   for explicit `/launch-closeout L3`.

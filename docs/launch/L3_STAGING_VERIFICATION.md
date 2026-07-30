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
| Railway deployment | `900b74fa-80cd-40d7-9a3a-5eba472f0fc6` (`SUCCESS`, restored forward deployment) |
| Railway deployment instance | `f13e12fc-33f5-40d3-bde1-1c3648bd8f81` (`RUNNING`) |
| API origin | `https://api-production-0641.up.railway.app` |
| Vercel team | `team_MVQMOaFtYHlwO5QVzSOZQ0Ud` |
| Vercel project | `the-coupon-staging` (`prj_r9VsE4xnCj53S3OiOUH7GSzQsn2c`) |
| Vercel deployment | `dpl_smnv3fDEV1EPYpyR2TDA56maiykS` (`READY`, created `2026-07-29T17:12:06Z`) |
| Web origin | `https://the-coupon-staging.vercel.app` |
| Source commit under test | `9f498675720fd74434102956a1301dfefc421063` |

The reviewed L3 implementation commit
`53334a1f47733ab32385f788e02a46bd65c59a61` was merged by PR #4 as source
commit `9f498675720fd74434102956a1301dfefc421063`. `/ship-staging` deployed that
source to the exact Railway and Vercel targets above.

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

These changes were reviewed in PR #4 and shipped through the target-specific
staging workflow. The launch phase remains open until explicit close-out.

## CI and local verification

- GitHub Actions merge run `30473285598` completed successfully at
  `2026-07-29T17:01:06Z` for source commit
  `9f498675720fd74434102956a1301dfefc421063`. Backend, frontend, deployment
  configuration, and production-bundle jobs were all green.
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

PR and merge CI both passed before shipment.

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

The pre-shipment membership UI finding was corrected in the reviewed source.
The post-shipment browser rerun returned all 15 members, promoted and demoted
the selected synthetic member with `204` responses, and visually confirmed the
admin controls in the final deployed bundle.

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

Post-shipment screenshots are stored locally under
`artifacts/launch-l3/20260729-postship/` and remain ignored by Git.

| UTC timestamp | File | SHA-256 |
| --- | --- | --- |
| `2026-07-29T17:16:07Z` | `members-admin.png` | `4042374e81b8364a26d43d81501fb2055f6b71ae1e583df1b1d36ff35b384b75` |
| `2026-07-29T17:16:19Z` | `picks-open.png` | `b65b622d4638721d95bb6ec942527beef4d4cf0abbb5ef0f048cd6bc88c88884` |
| `2026-07-29T17:24:45Z` | `pwa-update-banner.png` | `a5b0789f4829aef7b1a105aab71f88a52fd7b4f06c95793911f6ec5ce40c2c0d` |

The rollback-backed PWA transition changed the service-worker SHA-256 from
`5a3bf107e1a46178f71791142b4feaa9b1ef0188d1ef7da8b05410c7693e7e65`
to
`0cbc1054fef617b6e713f793558bd1cc9160a3a8372bbecee05e04037da02dc5`
and displayed the live five-second update banner.

## Scheduler evidence

Railway deployment metadata confirms one always-on API replica in
`europe-west4-drams3a`, with sleep disabled.

| Job | L3 result |
| --- | --- |
| `refresh_slate` | One successful manual execution at `2026-07-29T13:19:27Z`; the existing gameweek was refreshed idempotently. |
| `pick_reminders` | One successful manual execution at `2026-07-29T13:19:39Z`; it correctly found no open gameweek after settlement. |
| `lock_gameweeks` | One successful execution through the guarded lifecycle control; one gameweek locked. |
| `settle_gameweeks` | One initial execution left two picks pending, followed by one intentional retry that resolved both and settled the gameweek. |
| `connection_warmup` | One direct execution of the real job function completed successfully against the deployed service runtime. |
| `daily_backup` | One direct execution completed successfully at `2026-07-29T17:18:58Z`, creating a 209,052-byte PostgreSQL 17 logical backup. |

Two direct Railway SSH attempts at `refresh_slate` exited non-zero before a
database operation because a direct SSH child does not inherit the Nix loader
path used by PID 1. A subsequent service-runtime invocation supplied that path
and produced the single successful execution recorded above. The in-process
API remained ready throughout.

The original deployed backup failures identified the libpq URL and PostgreSQL
client-version defects. The reviewed fixes were shipped, and the successful
post-shipment execution above proves the deployed path.

## Log review and health

At the end of the run:

- API liveness returned HTTP `200` with status `ok`.
- Database readiness returned HTTP `200` with status `ready` and database
  status `ok`.
- The API SHA field is `unknown` on the current CLI-uploaded Railway
  deployment; deployment IDs and the inspected Vercel source commit are the
  release identifiers for this run.
- The final bounded Railway application-log scan on
  `900b74fa-80cd-40d7-9a3a-5eba472f0fc6` inspected 252 records on
  `2026-07-30`. Startup/migration errors, generated PIN values, synthetic
  profile names, bearer values, JWT shapes, PostgreSQL URLs, private-key
  headers, identity fields, and secret assignments each had zero matches.
- The static Vercel deployment produced no runtime records and no runtime
  errors in the final 24-hour check.
- The settlement-log change is present in the shipped source and records only
  non-personal outcome evidence.

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

The post-shipment scheduled backup and the earlier approved logical
export/restore exercise the corrected backup code paths against the same
PostgreSQL 17 schema. A final read-only query on `2026-07-30` confirmed
migration `004`, 15 profiles and memberships, two fixtures and picks, and zero
active push subscriptions.

## Rollback and forward restoration

Both exact staging targets completed a rollback and forward-restore rehearsal:

- Railway:
  `6b8ca99f-4423-48f3-a6ed-73d588ad8b95`
  (pre-shipment source) →
  `5dfccc34-279f-47cb-a3bd-943a09ab5933`
  (reviewed forward shipment) →
  `4fd323a5-b49c-4b68-a32b-09b4deb50927`
  (rollback) →
  `900b74fa-80cd-40d7-9a3a-5eba472f0fc6`
  (restored forward deployment).
- Vercel:
  `dpl_FX53BDv6KVPVzEwcknPsknATqSaA`
  (pre-remediation deployment) →
  `dpl_smnv3fDEV1EPYpyR2TDA56maiykS`
  (reviewed forward shipment) → the pre-remediation deployment → the reviewed
  forward shipment.

The final Railway instance is running the reviewed forward image with one
always-on replica, and the stable Vercel alias resolves to the reviewed forward
deployment. Root, SPA deep-link, security-header, service-worker-cache, CORS,
and database-readiness checks all pass.

## Final gate result

The owner explicitly confirmed successful push subscription, test delivery,
and unsubscribe on a supported real phone. The retained subscription record is
inactive (`active=0`), which matches the API's intentional unsubscribe model.
Temporary phone-test credentials were rotated and their refresh tokens
invalidated after the check.

`/launch-verify L3` returned **GREEN** on `2026-07-30` for the canonical branch
and final forward deployments. The full canned-odds story, exactly-one
scheduler exercise, platform-log review, disposable restore, evidence capture,
and tested rollback are complete. The top-level L3 status remains unchecked
until explicit `/launch-closeout L3`.

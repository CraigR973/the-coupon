# The Coupon — launch readiness and plan

Audit date: 2026-07-26

## Verdict

**Not ready to ship to a remote staging or production environment yet.**

The core game is implemented and locally verified, and the repository already
has a viable Railway container, Alembic migrations, health endpoints, a Vite
production build, and CI. Launch work is still required to close security and
frontend/API gaps, define the scheduler and backup topology, create fresh
infrastructure, and verify a real deployment.

No existing remote service or Betfair account was accessed during this audit.
The project-bound Supabase reference in `.codex/config.toml` must be treated as
unverified and must not be reused without explicit owner confirmation.

## Launch phase status

This checklist is the launch source of record. Only
`/launch-closeout <L0-L5>` may tick a phase after its gate is GREEN.

- [ ] **L0 — Owner decisions and project identity**
- [ ] **L1 — Launch-hardening implementation**
- [ ] **L2 — Fresh staging infrastructure**
- [ ] **L3 — Staging verification**
- [ ] **L4 — Fresh production infrastructure and owner checks**
- [ ] **L5 — Launch and first-Saturday watch**

## Recommended launch architecture

| Component | Staging | Production |
| --- | --- | --- |
| Web PWA | Separate Vercel project/environment | Vercel production project |
| API + scheduler | One always-on Railway replica | One always-on Railway replica |
| PostgreSQL | Fresh Supabase staging project | Fresh Supabase production project |
| Odds source | Explicit safe `FakeBetfair` mode | Betfair delayed app key + non-interactive certificate login |
| Domains | Stable staging web/API hostnames | Final web hostname + API subdomain |
| Monitoring | Railway logs + Sentry | Railway logs + Sentry + first-Saturday watch |

The single Railway replica is a deliberate MVP constraint. APScheduler runs
inside the API process, so scaling the API above one replica would duplicate
scheduled work. A dedicated scheduler service can replace this topology later.

## Default scope decisions

These are the lowest-risk defaults for the first launch unless the owner
chooses otherwise:

- Use Supabase as managed PostgreSQL only. Remove the incomplete avatar upload
  UI, unused browser Supabase client, and unused service-role-key requirement.
- Retain push notifications, but make the settings UI match the implemented
  `global_mute` and quiet-hours API rather than displaying unsupported
  per-category toggles.
- Use stable, separate frontend and API origins in each environment. Set an
  explicit absolute `VITE_API_URL` and exact `FRONTEND_ORIGIN`.
- Remove the unused passwordless device-activation flow until it has a complete
  browser route and token-storage flow. Retain display-name + PIN login.
- Add an admin-operated, one-time PIN reset flow and never place reset tokens,
  PINs, or credentials in application logs.
- Keep the embedded scheduler on one always-on API replica, and add settlement
  retries after Saturday night.

## Readiness already in place

- [x] All six build batches and local verification gates are closed
  (`STATUS.md`).
- [x] The Docker image installs PostgreSQL tools, copies the API and migrations,
  runs Alembic before Uvicorn, and fails startup if migration fails
  (`Dockerfile`).
- [x] Railway build, restart, and health-check configuration exists
  (`railway.toml`).
- [x] Async SQLAlchemy and Alembic disable prepared-statement caching for
  compatibility with Supabase transaction pooling
  (`apps/api/src/database.py`, `migrations/env.py`).
- [x] Liveness and database-readiness endpoints exist
  (`/api/v1/health` and `/api/v1/health/ready`).
- [x] Non-development secret validation, production API-doc disabling, API
  security headers, structured logs, and optional Sentry integration exist.
- [x] Game locks are stored in UTC and scheduler wall-clock jobs use
  `Europe/London`.
- [x] Test-only browser controls are not copied into the production image.
- [x] GitHub CI runs backend checks, migrations, frontend checks, and a
  production build.

## Blocking findings

### Application and security

- [ ] Implement durable PIN lockout using `failed_login_count` and
  `locked_until`, reject inactive profiles during login, and test rate limiting
  through Railway's proxy. Current counters are process-local and reset on
  restart (`apps/api/src/rate_limit.py`, `apps/api/src/routers/auth.py`).
- [ ] Replace the PIN-reset endpoint that writes a usable reset JWT to logs.
  Use the existing league-admin reset capability through a reviewed UI or a
  secure one-off operator command.
- [ ] Resolve the avatar contract. The frontend calls
  `/api/v1/auth/me/avatar`, but the API has no matching route or profile field.
  The recommended MVP action is to remove upload controls and retain generated
  initials.
- [ ] Align notification settings. The frontend expects nine category flags,
  while the API persists and returns only `global_mute` and quiet hours.
- [ ] Remove or complete passwordless activation. The API creates
  `/activate?code=...` links, but the frontend has no `/activate` route or
  device-token consumer.
- [ ] Create an idempotent, operator-only bootstrap command for the real player
  profiles, the `the-coupon` league, and memberships. The current seed creates
  only a hard-coded `Admin` profile.
- [ ] Remove dead inherited configuration and dependencies, including unused
  `ANTHROPIC_*`, backend Supabase client settings, `resend`, and the unused
  browser Supabase client, unless a launch feature needs them.
- [ ] Pin Python production dependencies so rebuilding the same commit is
  reproducible.

### Database and backups

- [ ] Provision new, separate staging and production Supabase projects. Do not
  infer that the committed project reference belongs to The Coupon.
- [ ] Lock down the Supabase Data API. The app uses custom JWTs and direct
  PostgreSQL access, not Supabase Auth. Enable RLS on every application table
  and deny `anon`/`authenticated`, or remove the application schema from the
  exposed Data API and revoke its grants. Verify the effective grants after
  migration.
- [ ] Choose the correct Supabase connection mode for the Railway network and
  encode it as a SQLAlchemy `postgresql+asyncpg://` URL with SSL. Use the direct
  connection when reachable or Supavisor session mode for a persistent IPv4
  backend; reserve transaction mode for a proven need.
- [ ] Replace `/tmp` application backups with Supabase managed backups/PITR or
  durable encrypted offsite storage. Document and rehearse one restore before
  production.
- [ ] Move migrations out of concurrent web startup before ever increasing the
  API above one replica. The one-replica MVP may retain migration-on-start.

### Scheduler and Betfair

- [ ] Enforce exactly one always-on Railway API replica with serverless/sleep
  disabled and `SCHEDULER_ENABLED=true`.
- [ ] Add Sunday/Monday settlement retries so a late market or a missed
  Saturday 22:00 run does not wait a week.
- [ ] Make one-off scheduled commands return a non-zero exit status on internal
  failure before relying on Railway Cron for any job.
- [ ] Add the missing scheduler, backup/restore, deploy, rollback, and incident
  runbooks referenced by the code and Railway configuration.
- [ ] Add an explicit staging-only canned-odds mode that production refuses to
  start with. Never deploy the test-control application.
- [ ] Implement Betfair non-interactive certificate login for unattended
  scheduled work. The current client supports only username/password login.
- [ ] Use the owner's delayed/read-only Betfair application key, confirm the
  target competition names, and keep all credentials/certificates in sealed
  backend secrets.
- [ ] The owner alone performs the real slate and price check. Automated agents
  must not log into the live account.

### Vercel, API routing, and CI

- [ ] Add Vercel configuration for the `apps/web` root, `dist` output, SPA
  deep-link rewrite, frontend security headers, and cache behavior.
- [ ] Standardize API URL handling. `api.ts` describes empty-string same-origin
  mode, while `AuthContext.tsx` rejects it, and no proxy rewrite exists.
- [ ] Configure exact staging and production CORS origins. The API currently
  accepts one `FRONTEND_ORIGIN`, so arbitrary Vercel preview URLs will not work.
- [ ] Change Railway's health check to `/api/v1/health/ready` so a deployment is
  not marked ready while PostgreSQL is unavailable.
- [ ] Require `ENVIRONMENT` explicitly outside local development; a missing
  value currently defaults to development and weakens production safeguards.
- [ ] Add a Docker-image build and Playwright production-bundle job to CI.
- [ ] Add staging post-deploy smoke tests for deep links, auth, league
  administration, picks, lock, settlement, push subscription, and PWA update
  behavior.

## Environment contract

### Railway backend

| Variable | Requirement |
| --- | --- |
| `DATABASE_URL` | Required secret; SQLAlchemy asyncpg URL with SSL |
| `JWT_ACCESS_SECRET` | Required, unique, generated secret |
| `JWT_REFRESH_SECRET` | Required, unique, generated secret |
| `ENVIRONMENT` | Required: `staging` or `production` |
| `FRONTEND_ORIGIN` | Required exact HTTPS frontend origin |
| `BF_APP_KEY` | Required in production; owner supplies delayed key |
| `BF_USER`, `BF_PASS` | Backend-only Betfair credentials |
| Future certificate variables | Required for non-interactive production login |
| `VAPID_PUBLIC_KEY` | Required while push is retained |
| `VAPID_PRIVATE_KEY` | Required secret while push is retained |
| `VAPID_CONTACT_EMAIL` | Required non-placeholder contact |
| `SCHEDULER_ENABLED` | Explicit `true` for the single-replica topology |
| `SENTRY_DSN_BACKEND` | Recommended |
| `LOG_LEVEL` | `INFO` initially |
| `PORT`, `RAILWAY_GIT_COMMIT_SHA` | Railway supplied |

`ADMIN_PIN` is a one-off bootstrap input, not a persistent service variable.
Remove the unused `SUPABASE_*` and `ANTHROPIC_*` variables under the recommended
MVP scope.

### Vercel frontend

| Variable | Requirement |
| --- | --- |
| `VITE_API_URL` | Required absolute HTTPS API URL for the selected environment |
| `VITE_VAPID_PUBLIC_KEY` | Required while push is retained |
| `VITE_SENTRY_DSN` | Recommended |

Never put database credentials, JWT secrets, Betfair credentials, a VAPID
private key, certificate private material, or a Supabase service-role key in a
`VITE_*` variable.

## Ordered launch work

### L0 — Owner decisions and project identity

- [ ] Confirm the recommended MVP scope decisions above.
- [ ] Choose the production domain and stable staging hostnames.
- [ ] Choose project names, account/team ownership, region, budget limits, and
  the initial player roster.
- [ ] Create a new private Git remote and record it as `origin`.
- [ ] Document whether launch phases integrate through local fast-forward or a
  remote PR/required-CI workflow.
- [ ] Confirm or replace the Supabase MCP project reference before any connector
  is allowed to access it.

**Gate:** repository ownership, domains, and every external target are explicit;
no existing service is being reused by inference.

### L1 — Launch-hardening implementation

- [ ] Complete every Application and security blocker.
- [ ] Complete the Vercel/API-routing code changes.
- [ ] Complete scheduler retry/failure behavior and non-interactive Betfair
  support behind tests.
- [ ] Add the bootstrap command, RLS/grant migration, pinned dependencies,
  runbooks, and CI coverage.
- [ ] Run the full local verification suite against clean PostgreSQL.

**Gate:** no known broken production UI surface; auth protections, database
exposure, config validation, and scheduled failure behavior are tested.

### L2 — Fresh staging infrastructure

- [ ] Provision a fresh Supabase staging project and verify Data API lockdown.
- [ ] Provision one always-on Railway staging service from the root Dockerfile.
- [ ] Provision the Vercel staging project with `apps/web` as its root.
- [ ] Configure environment-scoped secrets without copying production values.
- [ ] Apply migrations, run the non-real staging seed, and attach stable staging
  web/API domains.
- [ ] Replace the placeholder `/ship-staging` workflow with the documented,
  target-specific deployment and rollback procedure.

**Gate:** readiness is green, the migration revision is current, and no
production credential or real member data exists in staging.

### L3 — Staging verification

- [ ] Run CI and the production-bundle Playwright flow against staging.
- [ ] Verify SPA deep links and refreshes, auth/PIN lockout, league membership,
  unique picks, locking, settlement retries, standings, and combined coupon.
- [ ] Verify push subscribe/send/unsubscribe on at least one supported phone.
- [ ] Verify logs and Sentry contain no PINs, tokens, names, or credentials.
- [ ] Exercise scheduler jobs once and confirm there is only one execution.
- [ ] Complete a backup restore rehearsal into a disposable database.
- [ ] Record screenshots, deployment identifiers, and verification evidence.

**Gate:** staging passes the full story with canned odds and a tested rollback.

### L4 — Fresh production infrastructure and owner checks

- [ ] Provision separate fresh production Supabase, Railway, and Vercel targets.
- [ ] Configure sealed production secrets and the delayed Betfair app key.
- [ ] Apply migrations and verify RLS/grants, readiness, logs, and Sentry.
- [ ] Run the idempotent bootstrap with the reviewed real roster; distribute
  PINs out of band.
- [ ] Attach production DNS and validate TLS without sending member invites yet.
- [ ] Owner performs the non-interactive Betfair certificate/slate/price probe.
- [ ] Replace the placeholder `/ship-prod` workflow with explicit promotion,
  health verification, and rollback steps.

**Gate:** owner approves the real slate, all services are healthy, and rollback
and restore procedures are available.

### L5 — Launch and first-Saturday watch

- [ ] Send member invites and confirm one login per supported device class.
- [ ] Confirm the Monday-Saturday slate refreshes and Saturday reminder.
- [ ] Watch the 14:30 Europe/London lock and all settlement retries.
- [ ] Confirm standings and combined coupon after settlement.
- [ ] Review errors, failed pushes, Betfair auth refreshes, database connections,
  and backup completion.
- [ ] Record launch results and any follow-up work separately from the completed
  build batches.

**Gate:** the first live gameweek is settled correctly and recoverability is
confirmed.

## Platform notes verified during the audit

- Supabase documents direct connections for persistent IPv6-capable backends,
  session-mode Supavisor for persistent IPv4-only backends, and transaction mode
  for temporary/serverless clients:
  <https://supabase.com/docs/guides/database/connecting-to-postgres>
- Supabase's 2026 Data API change makes table exposure opt-in for new projects;
  grants and RLS must still be verified explicitly:
  <https://supabase.com/changelog?types=breaking-change>
- Vercel requires an SPA rewrite for Vite deep links:
  <https://vercel.com/docs/frameworks/frontend/vite>
- Railway Cron is UTC, has a five-minute minimum, may run a few minutes late,
  and skips an invocation while the previous one is active:
  <https://docs.railway.com/cron-jobs>
- Betfair recommends certificate-based non-interactive login for autonomous
  scheduled applications and a delayed key for read-only use:
  <https://support.developer.betfair.com/hc/en-us/articles/115003899492-How-do-I-login-to-the-API>
  and
  <https://support.developer.betfair.com/hc/en-us/articles/25033076334748-What-is-read-only-Betfair-API-access>

## Workflow rule

This document plans launch work; it does not close a build batch. Use
`/launch-start <L0-L5>`, `/launch-verify <L0-L5>`, and explicit
`/launch-closeout <L0-L5>` for launch phases. Do not commit, merge, deploy, seed
a remote database, update either ship workflow, or mark a launch gate complete
unless the owner explicitly invokes the corresponding workflow.

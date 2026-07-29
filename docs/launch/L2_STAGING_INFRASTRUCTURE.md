# L2 — staging infrastructure record

Started: 2026-07-27

This is the non-secret implementation record for L2. It does not mark the
phase complete. Only `/launch-closeout L2` may close the gate.

## Supabase staging

- Organization: `CraigR973's Org` (`eufhjqkyoiuzfwuptlyn`).
- Project: `the-coupon-staging` (`gegcnhoeudpkcoxqcebe`).
- Region: London (`eu-west-2`).
- Plan: Free (`$0`). The owner made a staging-only exception to L0's planned
  Pro/Micro topology after freeing a project slot. This project may pause and
  does not include managed daily backups; production funding and restore
  requirements remain an L4 decision.
- Connection: the Railway service uses the project's direct PostgreSQL
  endpoint over IPv6. The connection string is held only as the encrypted
  Railway `DATABASE_URL` value.
- Migration revision: `004`.
- Repository MCP: project-scoped, read-only, and limited to database,
  debugging, development, and documentation capabilities.

The first connector-created project (`jienwiqgnkknplpdnped`) was empty but did
not expose a usable database password. It was deleted and replaced with the
current project before any application data existed.

### Database lockdown evidence

- All 13 tables in `public`, including `alembic_version`, have RLS enabled and
  forced.
- `anon` and `authenticated` have no `public` schema usage and no application
  table, sequence, or function privileges.
- `PUBLIC` function execution is revoked and future objects inherit locked-down
  default privileges.
- `set_updated_at()` has a fixed `pg_catalog` search path.
- The Data API returned `401` for an application-table request made with the
  project's publishable key.
- Supabase security advisors report no warning or error. The only database
  advisor result is the expected informational `rls_enabled_no_policy` entry
  for the inaccessible `alembic_version` table.

### Synthetic seed

The idempotent staging bootstrap ran with generated values that were not
printed or stored in the repository:

| Object | Count |
| --- | ---: |
| Synthetic profiles with bcrypt PIN hashes | 15 |
| League | 1 |
| Memberships | 15 |
| Gameweeks, fixtures, and picks | 0 |

No production credential, real member roster, real PIN, or live Betfair data
was copied into the project.

## Railway staging

- Workspace: `Craig Robinson's Projects`
  (`518ea7c5-7ee6-464b-bcf0-befed3153c1f`), Hobby plan.
- Project: `the-coupon-staging`
  (`cc2fc994-87c3-4e2e-8d9b-5bcafa496350`).
- Environment: `production`
  (`333ffc77-ad0d-43af-8436-4865fb9c2946`). This name is Railway's default
  environment inside the dedicated staging project; it is not the Coupon
  production environment.
- Service: `api` (`535e77d7-f8a2-4fd4-85a3-e8cb0ada7fd8`).
- Service instance:
  `b1a74146-0d42-4c81-bdfc-444d43d8f826`.
- Current deployment:
  `6b8ca99f-4423-48f3-a6ed-73d588ad8b95`.
- Current deployment instance:
  `89f51f6b-fb26-4d20-8b4f-1b565aa3e59c`.
- Stable API origin:
  `https://api-production-0641.up.railway.app`.

The active deployment uses the repo-root `nixpacks.toml` and
`railway.toml`. Nixpacks installs the pinned API dependencies into
`/opt/venv`; startup applies Alembic before Uvicorn. Deployment metadata
confirms exactly one always-on Amsterdam replica, IPv6 egress, a
`/api/v1/health/ready` health check, restart-on-failure with three retries,
0.25 vCPU, 500 MB memory, and a 1,000-process limit. The instance is `RUNNING`.

Both liveness and database readiness return HTTP `200`; readiness reports
`{"status":"ready","db":"ok"}`. A CORS preflight from the stable Vercel origin
returns HTTP `200`, the exact origin, and credential support.

Configured application variable names are:

- `BF_FAKE_MODE`
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

Values are sealed in Railway and are not recorded here. `BF_FAKE_MODE=true`;
there is no Betfair account login or production Betfair credential in staging.

Railway usage limits are workspace-wide and would also affect unrelated
projects, so the owner approved a staging exception to L0's proposed shared
workspace hard stop. The API instead has the service-level CPU and memory caps
above. Projected workspace usage after staging is approximately `$9.50/month`
and remains usage-based.

## Vercel staging

- Team: `craigr973's projects`
  (`team_MVQMOaFtYHlwO5QVzSOZQ0Ud`), Hobby plan.
- Project: `the-coupon-staging`
  (`prj_r9VsE4xnCj53S3OiOUH7GSzQsn2c`).
- Git repository and production branch: `CraigR973/the-coupon`, `main`.
- Root directory: `apps/web`.
- Node.js runtime: `20.x`.
- Current production deployment:
  `dpl_4N6VvjxvmfJM64Ee1YepRNyxPNKG`.
- Immutable deployment URL:
  `https://the-coupon-staging-evhlo3tp9-craigr973s-projects.vercel.app`.
- Stable web origin:
  `https://the-coupon-staging.vercel.app`.

The current deployment is `READY`. Production-scoped
`VITE_API_URL` and `VITE_VAPID_PUBLIC_KEY` are encrypted in Vercel. The stable
root and `/join/test-code` deep link both return HTTP `200` with the same SPA
asset, and the committed security and cache headers are present.

Vercel reports that Node.js 20 builds will stop after 2026-10-01. Updating the
runtime is follow-up work because the current repository toolchain explicitly
pins Node.js 20.

## Rollback baselines

- Backend: Railway deployment
  `6b8ca99f-4423-48f3-a6ed-73d588ad8b95`.
- Frontend: Vercel deployment
  `dpl_4N6VvjxvmfJM64Ee1YepRNyxPNKG`.

The target-specific `/ship-staging` workflow captures the prior healthy IDs
before every shipment, deploys only these recorded targets, and verifies
readiness, migration state, CORS, and SPA deep links. Database migrations are
forward-only unless a separately reviewed recovery plan exists.

## Gate state

The L2 implementation evidence is present: readiness is green, the database is
at revision `004`, the public schema and Data API are locked down, and staging
contains only synthetic data and newly generated staging credentials.

The phase remains unchecked pending `/launch-verify L2` and explicit
`/launch-closeout L2`.

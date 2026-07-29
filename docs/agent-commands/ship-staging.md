---
description: Ship a reviewed main-branch commit to The Coupon's exact staging targets.
---

# /ship-staging

Deploy only the targets recorded below. Do not use an ambient CLI project link,
create infrastructure, copy production values, or substitute another target.

| Platform | Exact staging target |
| --- | --- |
| Supabase | `the-coupon-staging` (`gegcnhoeudpkcoxqcebe`) |
| Railway project | `the-coupon-staging` (`cc2fc994-87c3-4e2e-8d9b-5bcafa496350`) |
| Railway environment | `production` (`333ffc77-ad0d-43af-8436-4865fb9c2946`) in the dedicated staging project |
| Railway service | `api` (`535e77d7-f8a2-4fd4-85a3-e8cb0ada7fd8`) |
| Railway API origin | `https://api-production-0641.up.railway.app` |
| Vercel team | `craigr973's projects` (`team_MVQMOaFtYHlwO5QVzSOZQ0Ud`) |
| Vercel project | `the-coupon-staging` (`prj_r9VsE4xnCj53S3OiOUH7GSzQsn2c`) |
| Vercel web origin | `https://the-coupon-staging.vercel.app` |

The Railway environment's name is `production` only because it is the default
environment inside a dedicated staging project. It is not the Coupon
production target.

## 1. Preflight

1. Read `docs/launch/L2_STAGING_INFRASTRUCTURE.md` and `STATUS.md`.
2. Require a clean `main` worktree. Stop rather than stashing, discarding,
   switching, or deploying unreviewed changes:

   ```bash
   git -C /Users/craigrobinson/the-coupon status --porcelain
   git -C /Users/craigrobinson/the-coupon symbolic-ref --short HEAD
   git -C /Users/craigrobinson/the-coupon rev-parse HEAD
   ```

3. Confirm the project IDs above with read-only Railway and Vercel inspection.
   Stop on any mismatch. Never infer targets from `.railway`, `.vercel`, or
   cached CLI state.
4. Confirm the required Railway variable names without displaying their
   values:
   `BF_FAKE_MODE`, `DATABASE_URL`, `ENVIRONMENT`, `FRONTEND_ORIGIN`,
   `JWT_ACCESS_SECRET`, `JWT_REFRESH_SECRET`, `LOG_LEVEL`,
   `SCHEDULER_ENABLED`, `VAPID_CONTACT_EMAIL`, `VAPID_PRIVATE_KEY`, and
   `VAPID_PUBLIC_KEY`. Secret-bearing Railway variable commands include raw
   values; pipe their output into a local key-only validator and never echo,
   log, or return the raw output.
5. Confirm Vercel production has encrypted `VITE_API_URL` and
   `VITE_VAPID_PUBLIC_KEY`. Do not print or download their values.
6. Capture the current healthy Railway and Vercel production deployment IDs.
   These are the rollback targets. The initial L2 baselines are:
   - Railway: `6b8ca99f-4423-48f3-a6ed-73d588ad8b95`
   - Vercel: `dpl_4N6VvjxvmfJM64Ee1YepRNyxPNKG`
7. Use `$ARGUMENTS` as the deployment message when non-empty; otherwise use
   `ship staging <short-commit-sha>`.

## 2. Verify the source

Run the CI-equivalent backend, migration, frontend, and deployment-config
checks from the clean checkout. Start database-backed tests from a clean
scratch PostgreSQL schema because the HTTP pick-flow test commits. Stop if any
check fails.

At minimum, run Ruff check and format verification, mypy, the full API test
suite, frontend lint/typecheck/tests/build, the deployment-config assertions in
`.github/workflows/ci.yml`, and `git diff --check`.

## 3. Deploy the API

Run Railway from the repository root with every selector explicit:

```bash
/Users/craigrobinson/.nvm/versions/node/v20.20.2/lib/node_modules/@railway/cli/bin/railway \
  up /Users/craigrobinson/the-coupon \
  --project cc2fc994-87c3-4e2e-8d9b-5bcafa496350 \
  --environment 333ffc77-ad0d-43af-8436-4865fb9c2946 \
  --service 535e77d7-f8a2-4fd4-85a3-e8cb0ada7fd8 \
  --detach --json --message "<deployment-message>"
```

Capture the new deployment ID. Poll its status with the same explicit project,
environment, and service selectors until it is `SUCCESS`, or stop and roll
back if it reaches a terminal failure:

```bash
/Users/craigrobinson/.nvm/versions/node/v20.20.2/lib/node_modules/@railway/cli/bin/railway \
  deployment list \
  --project cc2fc994-87c3-4e2e-8d9b-5bcafa496350 \
  --environment 333ffc77-ad0d-43af-8436-4865fb9c2946 \
  --service 535e77d7-f8a2-4fd4-85a3-e8cb0ada7fd8 \
  --limit 5 --json
```

Verify the new deployment metadata still specifies one replica in
`europe-west4-drams3a`, serverless sleep disabled, IPv6 egress enabled,
0.25 vCPU, 500 MB memory, and `/api/v1/health/ready`.

Fetch a bounded log snapshot for the new deployment. Inspect it in memory for
migration/startup errors and for PIN, token, credential, connection-string, or
real-name leakage. Report only pass/fail findings and counts, never raw
secret-bearing log lines.

Verify:

```text
GET https://api-production-0641.up.railway.app/api/v1/health
GET https://api-production-0641.up.railway.app/api/v1/health/ready
```

Both must return HTTP `200`, and readiness must report database status `ok`.
Use Railway's scoped variables with the repository API virtualenv to run
`alembic current`; it must equal the repository's sole head. Do not run a
downgrade.

## 4. Deploy the web app

Deploy from the repository root. The Vercel project already has `apps/web` as
its configured root, so passing `apps/web` as the upload root would incorrectly
produce `apps/web/apps/web`.

```bash
PATH="/Users/craigrobinson/.nvm/versions/node/v20.20.2/bin:$PATH" \
vercel deploy /Users/craigrobinson/the-coupon \
  --prod --yes --archive=tgz --format=json \
  --project prj_r9VsE4xnCj53S3OiOUH7GSzQsn2c \
  --scope team_MVQMOaFtYHlwO5QVzSOZQ0Ud
```

Capture the new Vercel deployment ID and immutable URL. Require `READY` and
confirm that the stable alias remains
`https://the-coupon-staging.vercel.app`.

## 5. Smoke the combined deployment

1. Require HTTP `200` from the stable web root and `/join/test-code`.
2. Confirm both routes serve the same SPA asset and retain the committed
   security/cache headers.
3. Send an `OPTIONS` preflight to an API route with
   `Origin: https://the-coupon-staging.vercel.app`. Require HTTP `200`,
   `Access-Control-Allow-Origin` equal to that exact origin, and credentials
   enabled.
4. Recheck API readiness after the frontend promotion.
5. Report the source commit, previous and new deployment IDs, stable URLs,
   migration revision, and smoke results. Do not print environment values or
   update `launch-log.md`; launch logs are updated only by an explicit launch
   close-out workflow.

## 6. Rollback

Rollback never downgrades the database. If a forward migration is incompatible
with the previous application, stop and use a reviewed recovery plan.

To restore the previous Vercel production deployment:

```bash
PATH="/Users/craigrobinson/.nvm/versions/node/v20.20.2/bin:$PATH" \
vercel rollback <previous-vercel-deployment-id> --yes \
  --scope team_MVQMOaFtYHlwO5QVzSOZQ0Ud
```

To restore the previous Railway deployment:

```bash
/Users/craigrobinson/.nvm/versions/node/v20.20.2/lib/node_modules/@railway/cli/bin/railway \
  api \
  'mutation Rollback($id: String!) { deploymentRollback(id: $id) }' \
  --variables '{"id":"<previous-railway-deployment-id>"}' --compact
```

After either rollback, poll the exact target to completion and repeat API
readiness, migration-head, stable web/deep-link, and CORS checks. Record both
the failed and restored deployment IDs in the shipment report.

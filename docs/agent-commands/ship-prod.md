---
description: Promote a reviewed main-branch commit to The Coupon's exact production targets.
---

# /ship-prod

Deploy only the targets recorded below. Do not use an ambient CLI project link,
create infrastructure, copy staging values, or substitute another target.

| Platform | Exact production target |
| --- | --- |
| Supabase project | `the-coupon-production` (`pugujiiojitstkilphrz`), London, Free plan — never to be attached to MCP |
| Railway project | `the-coupon-production` (`e030ebe3-e7fc-43c9-9478-4e80cafaa126`) |
| Railway environment | `production` (`8f18cb49-5137-4557-900a-031bcab4ac38`) |
| Railway service | `api` (`d59f4f17-3e7d-4b3b-bf40-30620150fa2f`) |
| Railway API origin | `https://api-production-109b1.up.railway.app` |
| Vercel team | `craigr973's projects` (`team_MVQMOaFtYHlwO5QVzSOZQ0Ud`) |
| Vercel project | `the-coupon-production` (`prj_3h3OSNFDoPAySqTa9nVswUrMs0jJ`) |
| Vercel web origin | intended alias `https://the-coupon-production.vercel.app`; exact alias must be confirmed and recorded after the first L4 deployment |

This workflow is deliberately fail-closed until L4 has a healthy initial
deployment. It must not be used to finish provisioning L4.

## 1. Preflight

1. Read `docs/launch/L4_PRODUCTION_INFRASTRUCTURE.md`, `STATUS.md`, and
   `docs/LAUNCH_PLAN.md`.
2. Require L4 to be checked, an exact Supabase project ref and confirmed Vercel
   alias to be present in the L4 record, and healthy Railway and Vercel rollback
   deployment IDs to be recorded. Stop if any item is absent.
3. Require a clean `main` worktree whose commit is present on `origin/main`.
   Stop rather than stashing, discarding, switching, or deploying unreviewed
   changes:

   ```bash
   git -C /Users/craigrobinson/the-coupon status --porcelain
   git -C /Users/craigrobinson/the-coupon symbolic-ref --short HEAD
   git -C /Users/craigrobinson/the-coupon rev-parse HEAD
   git -C /Users/craigrobinson/the-coupon rev-parse origin/main
   ```

4. Confirm every project, environment, service, domain, and project ref above
   with read-only platform inspection. Stop on any mismatch. Never infer a
   production target from `.railway`, `.vercel`, MCP, or cached CLI state.
   Production Supabase must never be attached to MCP.
5. Confirm the required Railway variable names without displaying values:
   `BF_APP_KEY`, `BF_CERT_FILE`, `BF_CERT_PEM_B64`, `BF_KEY_FILE`,
   `BF_KEY_PEM_B64`, `BF_PASS`, `BF_USER`, `DATABASE_URL`, `ENVIRONMENT`,
   `FRONTEND_ORIGIN`, `JWT_ACCESS_SECRET`, `JWT_REFRESH_SECRET`, `LOG_LEVEL`,
   `SCHEDULER_ENABLED`, `VAPID_CONTACT_EMAIL`, `VAPID_PRIVATE_KEY`, and
   `VAPID_PUBLIC_KEY`. Require `BF_FAKE_MODE` to be absent or false.
   Secret-bearing variable commands include raw values; pipe output into a
   key-only in-memory validator and never echo, log, persist, or return raw
   output.
6. Confirm Vercel production has encrypted production-scoped `VITE_API_URL`
   and `VITE_VAPID_PUBLIC_KEY`. Do not print or download their values.
7. Confirm the current migration revision. Do not look for a backup or restore
   point: under the owner's 2026-07-30 deferral, production has none. Instead,
   if this shipment introduces an Alembic revision, require a written forward
   recovery plan for it before deploying, because `nixpacks.toml` applies
   migrations automatically on boot and the change cannot be undone. Stop if
   the shipment migrates and no such plan exists.
8. Capture the current healthy Railway and Vercel deployment IDs from the exact
   targets above. These are this shipment's rollback baselines.
9. Use `$ARGUMENTS` as the deployment message when non-empty; otherwise use
   `ship production <short-commit-sha>`.

## 2. Verify the source

Run the CI-equivalent backend, migration, frontend, and deployment-config
checks from the clean checkout. Start database-backed tests from a clean
scratch PostgreSQL schema because the HTTP pick-flow test commits. Stop if any
check fails.

At minimum, run Ruff check and format verification, mypy, the full API test
suite, frontend lint/typecheck/tests/build, the deployment-config assertions in
`.github/workflows/ci.yml`, and `git diff --check`.

Do not run the test suite, destructive probes, or rollback rehearsals against
production. The owner performs any required live Betfair probe.

## 3. Deploy the API

Run Railway from the repository root with every selector explicit:

```bash
/Users/craigrobinson/.nvm/versions/node/v20.20.2/lib/node_modules/@railway/cli/bin/railway \
  up /Users/craigrobinson/the-coupon \
  --project e030ebe3-e7fc-43c9-9478-4e80cafaa126 \
  --environment 8f18cb49-5137-4557-900a-031bcab4ac38 \
  --service d59f4f17-3e7d-4b3b-bf40-30620150fa2f \
  --detach --json --message "<deployment-message>"
```

Capture the new deployment ID. Poll its status with the same explicit project,
environment, and service selectors until it is `SUCCESS`, or stop and roll
back if it reaches a terminal failure:

```bash
/Users/craigrobinson/.nvm/versions/node/v20.20.2/lib/node_modules/@railway/cli/bin/railway \
  deployment list \
  --project e030ebe3-e7fc-43c9-9478-4e80cafaa126 \
  --environment 8f18cb49-5137-4557-900a-031bcab4ac38 \
  --service d59f4f17-3e7d-4b3b-bf40-30620150fa2f \
  --limit 5 --json
```

Verify the new deployment metadata still specifies exactly one replica in
`europe-west4-drams3a`, serverless sleep disabled, IPv6 egress enabled,
0.25 vCPU, 500 MB memory, and `/api/v1/health/ready`.

Fetch a bounded log snapshot for the new deployment. Inspect it in memory for
migration/startup errors and for PIN, token, credential, connection-string,
certificate, private-key, or real-name leakage. Report only pass/fail findings
and counts, never raw secret-bearing log lines.

Verify:

```text
GET https://api-production-109b1.up.railway.app/api/v1/health
GET https://api-production-109b1.up.railway.app/api/v1/health/ready
```

Both must return HTTP `200`, and readiness must report database status `ok`.
Use Railway's scoped variables with the repository API virtualenv to run
`alembic current`; it must equal the repository's sole head. Recheck RLS and
effective `anon`/`authenticated`/`PUBLIC` grants with a direct production
database session that does not expose values. Do not use MCP or run a
downgrade.

## 4. Deploy the web app

Deploy from the repository root. The Vercel project already has `apps/web` as
its configured root, so passing `apps/web` as the upload root would incorrectly
produce `apps/web/apps/web`.

```bash
PATH="/Users/craigrobinson/.nvm/versions/node/v20.20.2/bin:$PATH" \
vercel deploy /Users/craigrobinson/the-coupon \
  --prod --yes --archive=tgz --format=json \
  --project prj_3h3OSNFDoPAySqTa9nVswUrMs0jJ \
  --scope team_MVQMOaFtYHlwO5QVzSOZQ0Ud
```

Capture the new Vercel deployment ID and immutable URL. Require `READY` and
confirm that the exact stable alias recorded in the L4 infrastructure record
still points to this deployment.

## 5. Smoke the combined deployment

1. Require HTTP `200` from the stable web root and a non-mutating SPA deep
   link.
2. Confirm both routes serve the same SPA asset and retain the committed
   security/cache headers.
3. Send an `OPTIONS` preflight to an API route with the exact recorded stable
   web origin. Require HTTP `200`, `Access-Control-Allow-Origin` equal to that
   origin, and credentials enabled.
4. Recheck API readiness and migration head after the frontend promotion.
5. Inspect bounded Railway and Vercel logs again and report only redacted
   pass/fail findings.
6. Report the source commit, previous and new deployment IDs, stable URLs,
   migration revision, backup/restore-point identity, and smoke results. Do not
   print environment values or update `launch-log.md`; launch logs are updated
   only by an explicit launch close-out workflow.

## 6. Rollback

Rollback never downgrades the database. If a forward migration is incompatible
with the previous application, stop and use a reviewed forward recovery plan.

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
readiness, migration-head, stable web/deep-link, CORS, and bounded redacted-log
checks. Record both the failed and restored deployment IDs in the shipment
report. Restore the database only under the separately reviewed production
recovery procedure; never improvise a destructive restore during rollback.

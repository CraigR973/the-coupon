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
   Query the exact Railway service instance's `railwayConfigFile` field too.
   Require it to be null or empty; a non-empty legacy Config File setting would
   compete with `.railway/railway.ts`, so stop and clear that setting explicitly
   before continuing.
5. Confirm the required Railway variable names without displaying values:
   `DATABASE_URL`, `ENVIRONMENT`, `FRONTEND_ORIGIN`, `JWT_ACCESS_SECRET`,
   `JWT_REFRESH_SECRET`, `LOG_LEVEL`, `ODDS_API_BOOKMAKER`, `ODDS_API_KEY`,
   `ODDS_PROVIDER`, `SCHEDULER_ENABLED`, `VAPID_CONTACT_EMAIL`,
   `VAPID_PRIVATE_KEY`, and `VAPID_PUBLIC_KEY`.

   Under ADR 0002 the odds source is `oddsapi`, so `ODDS_API_KEY` is the
   credential that matters and the `BF_*` set is **not** required — `config.py`
   reads Betfair's certificate pair only when `odds_provider` is `betfair`. The
   eight `BF_*` variables still sealed from L1/L4 are inert; leave them or
   remove them deliberately, but do not treat their presence as a gate.

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

`scripts/ci-local.sh` runs exactly that set. Use it rather than trusting a green
tick on GitHub: Actions is not always scheduling runs (a major outage on
2026-08-06 let two pushes to main land with no run created at all), and a
*missing* run reads the same as a passing one unless you look for it. Confirm a
run exists for the commit being shipped — not merely that none failed.

Do not run the test suite, destructive probes, or rollback rehearsals against
production. The owner performs any required live Betfair probe.

## 3. Deploy the API

**The repository's Railway link points at `the-coupon-staging`**
(`cc2fc994-87c3-4e2e-8d9b-5bcafa496350`, API origin
`https://api-production-0641.up.railway.app`) — the same trap as `.vercel`
below, and easier to miss because the staging origin is also named
`api-production-*`. `railway status`, `logs`, `variables`, `redeploy`, and
`down` all act on **staging** when run from this repository without explicit
selectors. Every command in this section passes `--project`, `--environment`,
and `--service`, which is what makes it safe; never drop them, and never read
the deployed state from a bare `railway status`. For read-only inspection of
production outside this workflow, `railway api` takes the IDs as GraphQL
variables and needs no link at all.

Apply the reviewed Railway IaC before uploading source. `config plan` and
`config apply` do not accept selector flags, so the exact IDs are supplied as
environment variables; these override the repository's staging link. Write a
pinned plan, review its redacted output, and require that it changes only the
existing `api` service without deleting a resource or variable. Never pass
`--show-values`, `--decrypt-variables`, or `--confirm-destructive`. Railway's
TypeScript evaluator requires Node 22 or newer, independently of the web app's
Node 20 toolchain; require `nvm` to have a Node 22 release installed:

```bash
. /Users/craigrobinson/.nvm/nvm.sh --no-use
nvm use 22 --silent
RAILWAY_IAC_PLAN="$(mktemp /tmp/the-coupon-production-iac.XXXXXX.json)"
RAILWAY_PROJECT_ID=e030ebe3-e7fc-43c9-9478-4e80cafaa126 \
RAILWAY_ENVIRONMENT_ID=8f18cb49-5137-4557-900a-031bcab4ac38 \
RAILWAY_SERVICE_ID=d59f4f17-3e7d-4b3b-bf40-30620150fa2f \
/Users/craigrobinson/.nvm/versions/node/v20.20.2/lib/node_modules/@railway/cli/bin/railway \
  config plan --file /Users/craigrobinson/the-coupon/.railway/railway.ts \
  --out "$RAILWAY_IAC_PLAN"
```

Stop on an unexpected or destructive plan. Otherwise apply exactly that pinned
plan, still without `--confirm-destructive`, then remove the temporary plan:

```bash
. /Users/craigrobinson/.nvm/nvm.sh --no-use
nvm use 22 --silent
RAILWAY_PROJECT_ID=e030ebe3-e7fc-43c9-9478-4e80cafaa126 \
RAILWAY_ENVIRONMENT_ID=8f18cb49-5137-4557-900a-031bcab4ac38 \
RAILWAY_SERVICE_ID=d59f4f17-3e7d-4b3b-bf40-30620150fa2f \
/Users/craigrobinson/.nvm/versions/node/v20.20.2/lib/node_modules/@railway/cli/bin/railway \
  config apply --plan "$RAILWAY_IAC_PLAN" --yes
rm "$RAILWAY_IAC_PLAN"
```

Capture the deployment ID printed by `config apply`, when present, and poll it
to terminal `SUCCESS` before continuing. A failed IaC deployment stops the
shipment: restore the prior Railway deployment and do not upload source. This
serialization matters because both the old and new image run boot migrations
and the scheduler.

First stamp the commit being shipped so `/api/v1/health` can report what is
actually running. Railway injects `RAILWAY_GIT_COMMIT_SHA` only for
GitHub-connected services, and this one deploys by CLI, so it must be set
explicitly on every shipment or it goes stale and
`scripts/check-deploy-drift.sh` falls back to the weaker migration and probe
tiers:

```bash
/Users/craigrobinson/.nvm/versions/node/v20.20.2/lib/node_modules/@railway/cli/bin/railway \
  variables --set "RAILWAY_GIT_COMMIT_SHA=$(git -C /Users/craigrobinson/the-coupon rev-parse HEAD)" \
  --skip-deploys \
  --project e030ebe3-e7fc-43c9-9478-4e80cafaa126 \
  --environment 8f18cb49-5137-4557-900a-031bcab4ac38 \
  --service d59f4f17-3e7d-4b3b-bf40-30620150fa2f
```

**If anything after this point fails to deploy, set the variable back to the
commit that is actually running.** The stamp is applied *before* the upload, so a
failed or abandoned shipment leaves `/api/v1/health` claiming a commit production
is not serving — and `scripts/check-deploy-drift.sh` trusts that field, so it
reports `in sync` when it is not. That happened on 2026-08-20: Railway paused
deploys platform-wide between the stamp and the upload, and the variable claimed
`33191ba` for 36 minutes while `2f708c82` was serving. Reverting is safe with
`--skip-deploys`; a container already created keeps the env snapshot it started
with, so an in-flight deployment still reports its own commit correctly.

Then run Railway from the repository root with every selector explicit.
**`railway up` uploads the working directory, not the git commit** — re-check
`git status --porcelain` immediately before this line, or uncommitted work ships
to production:

```bash
/Users/craigrobinson/.nvm/versions/node/v20.20.2/lib/node_modules/@railway/cli/bin/railway \
  up /Users/craigrobinson/the-coupon \
  --project e030ebe3-e7fc-43c9-9478-4e80cafaa126 \
  --environment 8f18cb49-5137-4557-900a-031bcab4ac38 \
  --service d59f4f17-3e7d-4b3b-bf40-30620150fa2f \
  --detach --json --message "<deployment-message>"
```

Poll for a terminal status with a delay between requests; a tight loop against
the deployment API will rate-limit.

**When a deployment sits in `DEPLOYING` past its `healthcheckTimeout`, ask which
step is stalled before touching anything.** `deployment list` reports only
`DEPLOYING` and cannot localise it; the per-step breakdown can:

```bash
/Users/craigrobinson/.nvm/versions/node/v20.20.2/lib/node_modules/@railway/cli/bin/railway \
  api 'query E($id: String!) { deploymentEvents(id: $id, first: 10) { edges { node { step createdAt completedAt } } } }' \
  --variables '{"id":"<deployment-id>"}' --compact
```

A `HEALTHCHECK` event with `completedAt: null` while the container's own logs
show a clean start — uvicorn listening, scheduler up, the 10-minute
`run_connection_warmup` job reaching the database — is a **platform** stall, not
a bad image, and no amount of waiting on the image will fix it. Confirm by
attempting a retry: if deploys are paused, `railway up` refuses with
`{"code":"UPLOAD_FAILED","error":"Deploys have been paused due to an upstream
issue"}`. Production keeps serving the previous deployment throughout, so the
correct response is to wait for the platform, not to roll back — there is nothing
to roll back *to* that differs from what is already live.

While such a stall lasts, **two containers are running and both have
`SCHEDULER_ENABLED=true`**, against the "exactly one scheduler" invariant L3 and
L4 rest on. The hourly open/lock sweeps are idempotent status transitions and the
settlement sweeps no-op when nothing is settleable, but the 11:00 pick reminders
would double-notify every member. If a stall looks like it will outlast the next
reminder window, say so rather than waiting silently.

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
`/health` must report the `sha` just stamped, and its `migration` — the head
bundled in the image — must equal the repository's sole head. `/health/ready`
reports the head the *database* is at; the two must agree, and a disagreement
means the boot-time `alembic upgrade head` did not complete. Recheck RLS and
effective `anon`/`authenticated`/`PUBLIC` grants with a direct production
database session that does not expose values. Do not use MCP or run a
downgrade.

## 4. Deploy the web app

**Usually a no-op.** The Vercel project is connected to GitHub and auto-deploys
`main` on every push, so by the time this workflow runs the web app is normally
already serving the target commit. Check first — if production already serves
this commit, skip this section rather than minting a duplicate CLI deployment
and moving the alias off the GitHub-linked one.

**The repository's `.vercel/project.json` points at `the-coupon-staging`**
(`prj_r9VsE4xnCj53S3OiOUH7GSzQsn2c`). Any Vercel command without an explicit
target therefore acts on **staging**, silently — `vercel env ls` has no
`--project` flag and will read the wrong project. `vercel deploy` does accept
`--project`, which is why the command below is safe; for anything else, set
`VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` in the environment instead.

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

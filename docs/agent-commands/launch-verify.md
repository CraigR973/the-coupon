---
description: Verify one Coupon launch phase against its phase-specific gate.
---

# /launch-verify

`$ARGUMENTS` must be exactly one unchecked launch phase ID from `L0` through
`L5` in `docs/LAUNCH_PLAN.md`.

Verification is evidence-gathering. It does not close the phase, commit, merge,
push, deploy, or tick the launch status row.

## Common checks

1. Read `STATUS.md`, `docs/LAUNCH_PLAN.md`, the latest `launch-log.md` section,
   and the current phase diff.
2. Confirm:
   - the current branch is the canonical branch from
     `docs/agent-commands/launch-start.md`;
   - the status row is unchecked;
   - every earlier launch phase is checked;
   - the worktree contains only intended phase changes.
3. Read the phase section through its `**Gate:**` paragraph. Treat every item
   and the gate as acceptance criteria; never substitute a generic green test
   run for phase-specific evidence.
4. Resolve every external target by documented project/account/environment ID.
   Stop rather than infer a target from cached CLI or connector state.
5. Report every check, command, target environment, and result. Redact values
   of secrets, PINs, tokens, credentials, database URLs, private keys, and
   certificates.

## Phase gates

### `L0` — Owner decisions and project identity

- Confirm the owner has explicitly recorded the MVP scope decisions, domains,
  project/account ownership, region, budget controls, and initial roster
  handling.
- Confirm `origin` is the intended private repository without pushing.
- Confirm the Supabase connector project ID is either documented as the fresh
  Coupon project or has been replaced. Do not query an unconfirmed project.
- Confirm no external target was selected merely because a CLI was already
  linked or authenticated.

### `L1` — Launch-hardening implementation

- Run the complete backend and frontend gate from `/batch-verify`.
- Start clean scratch PostgreSQL, run `alembic upgrade head`, and rerun
  database-backed tests.
- Build the production Docker image.
- Run the production-bundle Playwright flow and retain screenshots.
- Verify API/frontend contracts for avatar removal, notification settings, PIN
  reset, activation removal, bootstrap behavior, and staging-only odds mode.
- Verify durable PIN lockout, inactive-user rejection, proxy-aware rate-limit
  identity, migration-level RLS/grant coverage, non-zero scheduled failure
  exits, settlement retries, production rejection of fake odds, secret
  redaction, and explicit production configuration.
- Verify dependency locking and the new operational runbooks.

### `L2` — Fresh staging infrastructure

- Operate only on the explicitly documented staging targets.
- Confirm staging and production project IDs are distinct.
- Confirm Railway has exactly one always-on replica, readiness uses
  `/api/v1/health/ready`, the migration revision is current, and the scheduler
  mode matches the plan.
- Confirm Vercel uses `apps/web`, the expected build/output settings, stable
  staging URLs, SPA deep-link routing, and staging-only public variables.
- Verify the Supabase Data API cannot read application tables as
  `anon`/`authenticated`.
- Verify staging contains no real member data or production/owner Betfair
  credentials.
- Confirm `/ship-staging` names exact targets and has health and rollback
  checks; it must no longer be a placeholder.

### `L3` — Staging verification

- Use only the designated staging environment and safe canned odds.
- Run the full production-bundle browser story: deep links, auth/lockout,
  league administration, unique picks, lock, settlement retries, standings,
  combined coupon, and PWA update behavior.
- Verify push subscribe/send/unsubscribe on a supported real device when the
  owner makes one available.
- Confirm exactly one execution of each scheduler job.
- Scan logs and Sentry for secrets and personal data.
- Restore the approved backup into a disposable database and verify its
  migration revision and representative row counts.
- Record screenshots, deployment IDs, timestamps, and rollback evidence.

### `L4` — Fresh production infrastructure and owner checks

- Use read-only verification against only the documented production targets.
- Confirm production and staging project IDs, databases, domains, secrets, and
  deployment aliases are distinct.
- Confirm TLS, readiness, migration revision, RLS/grants, one scheduler
  instance, backup policy, monitoring, and expected roster counts.
- Confirm production uses the delayed/read-only Betfair key and
  non-interactive certificate configuration by secret name only.
- Require the owner's explicit attestation for the real Betfair slate/price
  probe. The agent must not log in, invoke the probe, or inspect credentials.
- Confirm `/ship-prod` names exact promotion, verification, and rollback
  targets; it must no longer be a placeholder.

### `L5` — Launch and first-Saturday watch

- Confirm member access without exposing PINs or invite tokens.
- Correlate scheduler and application logs for slate refresh, reminder, the
  14:30 Europe/London lock, settlement retries, standings, and the combined
  coupon.
- Confirm failed pushes, Betfair session refreshes, database connections,
  monitoring, and backups are within the documented operating thresholds.
- Require owner confirmation that the displayed real slate, prices, results,
  and final standings are correct.
- Confirm recoverability evidence remains current.

## Result

Return one of:

- **GREEN** — every phase item and gate has evidence;
- **RED** — list each failed check and its evidence;
- **BLOCKED** — list the exact missing owner input, credential, external state,
  or target confirmation.

Do not mark a phase complete. A GREEN result waits for the user to invoke
`/launch-closeout $ARGUMENTS`.

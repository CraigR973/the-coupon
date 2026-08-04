# Rollback Runbook

Use the platform deployment history. Do not roll databases backward unless a
reviewed migration-specific plan exists. The exact staging IDs and CLI
commands are in `docs/agent-commands/ship-staging.md`.

1. Identify the last known-good frontend and backend deployment IDs.
2. Roll the frontend back in Vercel first when the issue is browser-only.
3. Roll the backend back in Railway when API readiness, migrations, scheduler,
   or the odds provider integration is failing.
4. Keep one backend replica during rollback.
5. Recheck `/api/v1/health/ready`, login, current gameweek, picks, standings,
   and combined coupon.
6. Record the bad deployment ID, restored deployment ID, impact window, and
   follow-up issue in `launch-log.md` during explicit close-out.

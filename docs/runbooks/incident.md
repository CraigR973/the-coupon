# Incident Runbook

## First Response

1. Identify whether the issue is frontend, API, database, scheduler, Betfair, or
   push notifications.
2. Preserve Railway and Vercel log links before rotating deployments.
3. Do not paste PINs, JWTs, Betfair credentials, certificate material, or player
   private data into issue trackers or logs.

## Triage Checks

- Frontend: open `/login`, `/forgot-pin`, and `/settings`.
- API: check `/api/v1/health` and `/api/v1/health/ready`.
- Database: confirm Supabase status, connection limits, and latest migration.
- Scheduler: confirm one replica and inspect recent scheduler log lines.
- Betfair: owner confirms live account/app-key state; agents do not log in to
  the owner account.

## Recovery

Use `docs/runbooks/rollback.md` for deployment rollback and
`docs/runbooks/backup-restore.md` for database restore rehearsal or recovery.

# Backup And Restore Runbook

Supabase managed backups/PITR are the production backup source of record. The
old application `/tmp` backups are not durable enough for launch recovery.

## Backup Checks

1. Confirm managed backups or PITR are enabled for the target Supabase project.
2. Confirm the retention window with the owner before production launch.
3. Record the latest successful backup timestamp before first Saturday.

## Restore Rehearsal

1. Restore into a disposable database, never over staging or production.
2. Apply any pending migrations to head.
3. Run `/api/v1/health/ready` against the restored database.
4. Verify login, league membership, picks, standings, and combined coupon with
   test credentials.
5. Destroy the disposable database after evidence is recorded.

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

## Free-plan staging rehearsal

The staging Supabase project has no managed daily backup. For synthetic staging
data only, `scripts/agent/l3-logical-backup.py` provides a guarded logical
export and `scripts/agent/l3-restore-rehearsal.py` restores it into a fresh
pip-`pgserver` database.

- Export refuses to run unless `ENVIRONMENT=staging` and
  `ODDS_PROVIDER=fake`.
- Restore refuses non-loopback databases and requires
  `ENVIRONMENT=development`.
- The export is created mode `0600`, contains sensitive authentication hashes,
  and must never be committed or printed.
- Record only its SHA-256 checksum, migration revision, and table row counts.
- Delete the export after the rehearsal. The disposable database is removed
  automatically.

Run the export with the exact Railway staging selectors so only sealed staging
variables are supplied to the local process:

```bash
railway run \
  --project cc2fc994-87c3-4e2e-8d9b-5bcafa496350 \
  --environment 333ffc77-ad0d-43af-8436-4865fb9c2946 \
  --service 535e77d7-f8a2-4fd4-85a3-e8cb0ada7fd8 \
  --no-local -- \
  /Users/craigrobinson/app-starter/apps/api/.venv/bin/python \
  scripts/agent/l3-logical-backup.py export --output <mode-0600-path>
```

Then run:

```bash
/Users/craigrobinson/app-starter/apps/api/.venv/bin/python \
  scripts/agent/l3-restore-rehearsal.py --input <mode-0600-path>
```

This staging-only export does not replace the managed-backup/PITR requirement
for production.

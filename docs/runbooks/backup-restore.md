# Backup And Restore Runbook

**Production's only backup is the weekly off-site archive (Batch 95), and it is off until
the owner switches it on.** Supabase is on the Free plan: no managed backup and no PITR.
Batch 75 removed the old nightly dump because it wrote to `/tmp` and died with every
redeploy. The owner's choices on 2026-09-25: Cloudflare R2, EU jurisdiction, every
Monday at 04:00 London, built switched off.

## What the job does

`run_offsite_backup` (in `apps/api/src/scheduler.py`), in this order:

1. Resolves the target from the `BACKUP_*` variables, and fails naming any missing one.
2. Lists one key in the bucket, proving endpoint, key, bucket and clock before the
   database is read.
3. `pg_dump --format=custom --schema=public --no-owner` into a temporary directory. Grants
   and row-level-security policies stay in, so a Supabase restore brings the Data API
   lockdown back with the data.
4. Uploads `production/the-coupon-<UTC timestamp>.dump`, declaring its SHA-256 so R2
   refuses a corrupted body.

A failure writes `backup_failed` to the audit log and pushes "The weekly backup failed" to
every site admin, at most once a day. Each run moves about the database's size across
Supabase's egress: 17 MB on 2026-09-24.

## Switching it on (owner)

Only after the `/ship-prod` that carries Batch 95; before that the variables do nothing.

1. **Bucket.** Cloudflare dashboard, R2, Create bucket, Location: Specify jurisdiction,
   **EU**. The jurisdiction cannot be changed afterwards. Suggested name:
   `the-coupon-backups`.
2. **Bucket lock.** The bucket's Settings, Bucket lock rules, Add rule: prefix
   `production/`, retention **30 days**. R2 has no write-only key, so this is what stops a
   leaked key deleting or overwriting a recent backup.
3. **Lifecycle.** Settings, Object lifecycle rules: delete objects under `production/`
   after **90 days**, about twelve weekly archives. It must be longer than the lock.
4. **Key.** R2, Manage API tokens, Create: permission **Object Read & Write**, applied to
   that one bucket only. Note the Access Key ID and the Secret Access Key; the secret is
   shown once.
5. **Egress.** Supabase organisation, Usage: confirm egress has headroom. The consumer
   that exceeded the quota on 2026-08-25 was never identified (FEAT-A09).
6. **Railway, production `api` service.** Set, with the secret sealed:
   `BACKUP_S3_ENDPOINT=https://<account_id>.eu.r2.cloudflarestorage.com`,
   `BACKUP_S3_BUCKET`, `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`, and last
   `BACKUP_STORAGE=s3`. `BACKUP_S3_REGION` defaults to `auto` and `BACKUP_S3_PREFIX` to
   `production/`.
7. **Check.** The boot log must not say `offsite backup is switched on but misconfigured`.
   Then run it once rather than waiting for Monday, from `/app/apps/api` inside the
   container over `railway ssh`:
   `/opt/venv/bin/python -m src.run_scheduled offsite-backup`. The archive should appear
   in the bucket.

## Restoring

Into a **new, empty** database only — a new Supabase project in London, say. The command
drops and recreates the `public` schema, because the archive carries `CREATE SCHEMA
public` and every new database already has one.

1. Download the newest `production/the-coupon-*.dump` from the bucket.
2. Check it reads: `pg_restore --list the-coupon-<ts>.dump` must list
   `TABLE DATA public picks`.
3. Restore with a `pg_restore` of at least the dump's major version (production's image
   has 17):

   ```bash
   pg_restore --clean --if-exists --no-owner --exit-on-error \
     --dbname "<new database DSN>" the-coupon-<ts>.dump
   ```

4. Confirm `alembic_version` matches the head of the image you will run, point
   `DATABASE_URL` at the new database, deploy, and check `/api/v1/health/ready`.

`tests/test_offsite_backup.py` rehearses exactly this restore on every gate run: a settled
week is archived, restored into an empty database and compared table by table.

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

This staging-only export is a rehearsal tool, not production's backup; production's is
the weekly off-site archive above.

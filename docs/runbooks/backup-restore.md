# Backup And Restore Runbook

**Production's only backup is the weekly off-site archive (Batch 95), switched on
21 Nov 2026.** Supabase is on the Free plan: no managed backup and no PITR. Batch 75
removed the old nightly dump because it wrote to `/tmp` and died with every redeploy. The
owner's choices: EU storage, every Monday at 04:00 London, built switched off
(2026-09-25); Backblaze B2 rather than Cloudflare R2, on the account garmin-coach already
uses (2026-11-20). The first archive, 21 Nov 13:27 UTC, was 830,665 bytes.

## What the job does

`run_offsite_backup` (in `apps/api/src/scheduler.py`), in this order:

1. Resolves the target from the `BACKUP_*` variables, and fails naming any missing one.
2. Lists one key in the bucket, proving endpoint, key, bucket and clock before the
   database is read.
3. `pg_dump --format=custom --schema=public --no-owner` into a temporary directory. Grants
   and row-level-security policies stay in, so a Supabase restore brings the Data API
   lockdown back with the data.
4. Uploads `production/the-coupon-<UTC timestamp>.dump`, declaring its SHA-256
   (`x-amz-content-sha256`) so the store refuses a corrupted body. It sends no
   `Content-MD5` or `x-amz-checksum-*` header, which is why the bucket has no Object Lock
   (below).

A failure writes `backup_failed` to the audit log and pushes "The weekly backup failed" to
every site admin, at most once a day. Each run reads the table data across Supabase's
egress: about 4 MB on 2026-11-21, for a 20 MB database and a 0.8 MB archive.

## Switching it on (owner)

Done 20–21 Nov 2026 on Backblaze B2. The variables do nothing on an image without
Batch 95.

1. **Bucket.** Backblaze (an EU-region account), B2 Cloud Storage, Create a Bucket:
   private, default encryption on, **Object Lock off**. With a default retention, B2
   answers this job's upload with HTTP 400 `InvalidRequest`: it demands `Content-MD5` or
   an `x-amz-checksum-*` header the client does not send. Production's bucket:
   `the-coupon-backups-hm58yp`.
2. **Lifecycle.** One rule on prefix `production/`: hide after **90 days**, delete
   **30 days** after hiding. About twelve weekly archives stay visible, plus a month of
   hidden ones.
3. **Key.** Exactly `listBuckets`, `listFiles` and `writeFiles`, restricted to that bucket
   and the name prefix `production/`. Without `deleteFiles` a leaked key can at most hide
   an archive, and a hidden archive stays restorable for 30 days: the guarantee R2's
   30-day bucket lock gave. The console's key types are undocumented, so make it with the
   master key through the B2 CLI or the native `b2_create_key`:
   `b2 key create --bucket the-coupon-backups-hm58yp --name-prefix production/ the-coupon-backup listBuckets,listFiles,writeFiles`.
   On 20 Nov a local stdlib helper did this, checked the bucket and its rule, and proved
   the job's exact listing request returned 200; it is not in git.
4. **Egress.** Supabase organisation, Usage: confirm egress has headroom. The consumer
   that exceeded the quota on 2026-08-25 was never identified (FEAT-A09).
5. **Railway, production `api` service.** `BACKUP_S3_ENDPOINT=https://s3.<region>.backblazeb2.com`,
   `BACKUP_S3_REGION=<region>` (production: `eu-central-003`; the default `auto` is R2's
   and B2 refuses the signature), `BACKUP_S3_BUCKET`, `BACKUP_S3_ACCESS_KEY_ID` (the key
   ID), `BACKUP_S3_SECRET_ACCESS_KEY` (the application key), and last
   `BACKUP_STORAGE=s3`. `BACKUP_S3_PREFIX` defaults to `production/`. Seal the secret
   (from its three-dot menu) and deploy. To check the seal without seeing the value:
   `railway variables --json` with explicit selectors still lists a sealed variable, but
   with an empty value, so pipe it to a filter that prints only whether the secret's
   value is empty. On 21 Nov it came back with its value after the deploy (unsealed),
   then empty once sealed, with no redeploy, as payments' sealed `MONZO_*` secrets do.
   A cleared secret reads empty too; the next deploy's boot log tells the two apart,
   because a missing secret makes step 6's line appear, naming it.
   Then add every name set here to `PRESERVED_VARIABLE_NAMES` in `.railway/railway.ts`
   and to its copy in `scripts/assert-deployment-config.py` before the next
   `/ship-prod`. IaC replaces the service's variables as a set, so its plan deletes any
   name it does not preserve. On 22 Nov the plan for the two-game API shipment would have
   deleted all six, the sealed secret with them; the shipment stopped on it and the
   names were added.
6. **Check.** The boot log must not say `offsite backup is switched on but misconfigured`.
   Then run it once rather than waiting for Monday, inside the container over
   `railway ssh` with explicit selectors: `/opt/venv/bin/python -m src.run_scheduled
   offsite-backup` from `/app/apps/api`. The ssh shell lacks the image's
   `LD_LIBRARY_PATH` and `PYTHONPATH` and the image has no `mktemp`, so run it with the
   live process's environment (`/proc/1/environ`), at low priority: the container has
   0.25 vCPU and 512 MB. It logs `offsite backup complete` with the key and size. On
   21 Nov, 13:27 UTC: 830,665 bytes in 7 s, production's row counts identical before
   and after, memory peak 276 of 512 MB.

Cloudflare R2, the 2026-09-25 choice, works too: an EU-jurisdiction bucket with a 30-day
bucket lock on `production/`, a 90-day expiry, an Object Read & Write token for that one
bucket, and `BACKUP_S3_REGION` left at `auto`.

## Restoring

Into a **new, empty** database only — a new Supabase project in London, say. The command
drops and recreates the `public` schema, because the archive carries `CREATE SCHEMA
public` and every new database already has one.

1. Download the newest `production/the-coupon-*.dump` from the bucket. Backblaze's web
   console hands a selected file over as `backblaze_download_<timestamp>.zip` holding
   `production/<name>.dump`; check it holds exactly that one file, at the size the job
   logged, before extracting it.
2. Check it reads: `pg_restore --list the-coupon-<ts>.dump` must list
   `TABLE DATA public picks`.
3. Restore with a `pg_restore` of at least the dump's major version (production's image
   has 17). On Supabase you connect as `postgres`, which is not a superuser and cannot
   set `supabase_admin`'s default privileges. The archive carries three such entries,
   and `--exit-on-error` stops on the first ("permission denied to change default
   privileges") after the data is in. So leave them out with a list:

   ```bash
   pg_restore --list the-coupon-<ts>.dump \
     | grep -v 'DEFAULT ACL public DEFAULT PRIVILEGES FOR .* supabase_admin$' > restore.list
   pg_restore --clean --if-exists --no-owner --exit-on-error --use-list restore.list \
     --dbname "<new database DSN>" the-coupon-<ts>.dump
   ```

   Then, as `postgres`, `ALTER SCHEMA public OWNER TO pg_database_owner`, as Supabase
   had it; the restore recreates `public` owned by `postgres`. Supabase's own default
   privileges, for objects `supabase_admin` later creates in `public`, are not restored;
   this app creates none.
4. Confirm `alembic_version` matches the head of the image you will run, point
   `DATABASE_URL` at the new database, deploy, and check `/api/v1/health/ready`.

`tests/test_offsite_backup.py` rehearses exactly this restore on every gate run: a settled
week is archived, restored into an empty database and compared table by table.

## Restoring production in place (last resort)

Every write since the archive is lost, so the owner decides on the day that this
beats a forward fix. Before the two-game format is activated, prefer the lossless
undo in `migration-032-recovery.md`.

Needs:

- The archive's key, the SHA-256 of the downloaded copy and its revision, plus the
  `api` and `payments` deployment ids that ran that revision.
- A PostgreSQL 17 client with SSL. On the owner's Mac that is `~/.cache/the-coupon/pg17`,
  built 19 Nov 2026 against OpenSSL 4.1.0 in `~/.cache/the-coupon/openssl-4.1.0`; the
  system's OpenSSL 1.0.2 is too old. Keep both folders.
- Supabase's CA certificate (dashboard, Database settings, SSL configuration). The
  session pooler presents a chain to "Supabase Root 2021 CA", which no system bundle
  trusts, so connect with `sslmode=verify-full sslrootcert=<that file>`. With
  `require`, a TLS-intercepting proxy — this network has had one — would receive the
  password unnoticed. Fail closed; never fall back.

Steps:

1. **Keep the broken state.** Run the off-site backup once more; it lands in the
   bucket, where the backup key cannot delete it (a hidden copy stays 30 days).
2. **Stop writes.** `railway down` for `api`, then `payments`, with explicit project,
   environment and service.
3. **Restore.** Password in a 0600 `PGPASSFILE`, connection string without it:
   `DROP SCHEMA public CASCADE`, then the filtered `pg_restore` above, which recreates
   the schema with its grants and row-level-security policies, then
   `ALTER SCHEMA public OWNER TO pg_database_owner`.
4. **Audit.** The revision and row counts equal the archive's; RLS is forced on every
   table; no public-role table, schema or function grants remain.
5. **Matching code.** Roll `api` and then `payments` back to their deployments for that
   revision, poll both to SUCCESS, check `/health` and `/health/ready` agree, and set
   `RAILWAY_GIT_COMMIT_SHA` on both to that commit.
6. **Smoke and tell.** Web root, deep link, CORS preflight and the drift check; tell
   members what was lost and from when.

The outage is steps 2–5. Rehearsed 19 Nov on synthetic data and 21 Nov on the real
archive (27 tables, 17,780 rows), on local PostgreSQL 17, so the network to Supabase
comes on top: restore into an empty database 0.8 s; keep, drop and restore 2.4 s, every
table identical to the archive, the 031 API booted. A Supabase-shaped copy, with
`supabase_admin` the superuser and `postgres` not, showed the unfiltered restore failing
on the `supabase_admin` entries once the data was in, and the filtered one passing with
every table identical. Read from production on 21 Nov: no extension lives in `public`.
Still to read before relying on step 3: that production's `postgres` owns the database,
which dropping and recreating `public` needs.

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

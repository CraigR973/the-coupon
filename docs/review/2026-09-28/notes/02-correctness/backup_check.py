"""Batch 95: the weekly off-site backup, against a LOCAL fake S3 target (never R2).

The fake target is an httpx MockTransport that stores objects as files under the
scratchpad, refuses a body whose SHA-256 differs from the signed x-amz-content-sha256, and
re-derives the SigV4 Authorization header with the same secret to check it. The real
`run_offsite_backup()` runs with pg_dump from the pgserver install, against the scratch DB.
Then: restore the archive into a fresh database in the same cluster and compare contents,
and four misconfigurations (missing variable, unreachable, listing refused, upload refused).
"""

import asyncio
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
import httpx
import lib
from sqlalchemy import text

import src.scheduler as sched
from src.config import settings
from src.database import AsyncSessionLocal
from src.services import backup_storage as bs

OUT = "backup"
PGBIN = "/Users/craigrobinson/.cache/the-coupon/ci-local-venv/lib/python3.12/site-packages/pgserver/pginstall/bin"
os.environ["PATH"] = PGBIN + ":" + os.environ["PATH"]
STORE = lib.SCRATCH / "fake-s3"
PUSHES = lib.capture_pushes()


def fake_s3(mode: str = "ok"):
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(f"{req.method} {req.url.path}")
        if mode == "unreachable":
            raise httpx.ConnectError("no route to fake target", request=req)
        body = req.content
        # Re-derive the signature exactly as a store would, from what was sent.
        signed = {k: req.headers[k] for k in ("host", "x-amz-content-sha256", "x-amz-date")}
        expect = bs.authorization_header(
            method=req.method, path=req.url.raw_path.decode().split("?")[0], query=req.url.query.decode(),
            headers=signed, payload_sha256=req.headers["x-amz-content-sha256"],
            access_key_id="REVIEWKEY", secret_access_key="review-secret-value-0123456789",
            region="auto", service="s3", amz_date=req.headers["x-amz-date"])
        if req.headers.get("authorization") != expect:
            return httpx.Response(403, text="<Error><Code>SignatureDoesNotMatch</Code></Error>")
        if hashlib.sha256(body).hexdigest() != req.headers["x-amz-content-sha256"]:
            return httpx.Response(400, text="<Error><Code>XAmzContentSHA256Mismatch</Code></Error>")
        if req.method == "GET":
            if mode == "list403":
                return httpx.Response(403, text="<Error><Code>AccessDenied</Code></Error>")
            return httpx.Response(200, text="<ListBucketResult></ListBucketResult>")
        if req.method == "PUT":
            if mode == "put500":
                return httpx.Response(500, text="<Error><Code>InternalError</Code></Error>")
            dest = STORE / req.url.path.lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            return httpx.Response(200)
        return httpx.Response(405)

    return handler, calls


def configure(**over) -> None:
    base = dict(backup_storage="s3", backup_s3_endpoint="https://fake-s3.invalid", backup_s3_bucket="review-bucket",
                backup_s3_region="auto", backup_s3_access_key_id="REVIEWKEY",
                backup_s3_secret_access_key="review-secret-value-0123456789", backup_s3_prefix="review/")
    base.update(over)
    for k, v in base.items():
        setattr(settings, k, v)


async def attempt(label: str, mode: str = "ok", **over) -> None:
    configure(**over)
    handler, calls = fake_s3(mode)
    dumps = []
    real_archive = sched.create_archive

    async def counting_archive(url, dest):
        dumps.append(dest)
        return await real_archive(url, dest)

    orig_init = bs.S3BackupStore.__init__

    def init(self, target, *, transport=None):
        orig_init(self, target, transport=httpx.MockTransport(handler))

    sched.S3BackupStore.__init__ = init  # type: ignore[method-assign]
    sched.create_archive = counting_archive
    n_push = len(PUSHES)
    try:
        ok = await sched.run_offsite_backup()
    finally:
        sched.S3BackupStore.__init__ = orig_init  # type: ignore[method-assign]
        sched.create_archive = real_archive
    async with AsyncSessionLocal() as db:
        audit = (await db.execute(text("select changes from audit_log where action_type='backup_failed' order by timestamp desc limit 1"))).scalar_one_or_none()
    leaked = "review-secret-value" in str(audit)
    lib.out(OUT, f"[{label}] run_offsite_backup -> {ok}; store calls {calls}; pg_dump runs {len(dumps)}; "
                 f"latest backup_failed audit {audit if not ok else '(n/a)'}; secret in audit: {leaked}; admin pushes {[p['body'] for p in PUSHES[n_push:]]}")


async def main() -> None:
    shutil.rmtree(STORE, ignore_errors=True)
    async with AsyncSessionLocal() as db:
        await db.execute(text("delete from rate_limit_counters where bucket_key like 'alert:backup%'"))
        await db.commit()
    lib.out(OUT, "--- restore uses the runbook command: pg_restore --clean --if-exists --no-owner --exit-on-error ---")
    await attempt("configured, reachable")
    files = sorted(STORE.rglob("*.dump"))
    lib.out(OUT, f"objects in the fake bucket: {[str(f.relative_to(STORE)) + ' ' + str(f.stat().st_size) + 'B' for f in files]}")

    # Restore into a fresh database in the same cluster and compare.
    dsn = lib.STATE["database_url"].replace("postgresql+asyncpg://", "postgresql://")
    q = urlsplit(dsn).query
    admin = await asyncpg.connect(dsn)
    await admin.execute("drop database if exists restore_check")
    await admin.execute("create database restore_check")
    target = dsn.replace("/postgres?", "/restore_check?")
    r = subprocess.run([f"{PGBIN}/pg_restore", "--clean", "--if-exists", "--no-owner", "--exit-on-error", "-d", target, str(files[-1])], capture_output=True, text=True)
    lib.out(OUT, f"pg_restore exit {r.returncode} {r.stderr.strip()[:300]}")
    restored = await asyncpg.connect(target)
    checks = ["select count(*) from profiles", "select count(*) from leagues", "select count(*) from gameweeks",
              "select count(*) from picks", "select coalesce(sum(points_awarded),0) from picks",
              "select count(*) from audit_log where action_type <> 'backup_failed'", "select version_num from alembic_version",
              "select string_agg(status::text || ':' || coalesce(points_awarded,-1)::text, ',' order by id) from picks"]
    for sql in checks:
        a, b = await admin.fetchval(sql), await restored.fetchval(sql)
        lib.out(OUT, f"  {sql[:70]:70} source={str(a)[:40]} restored={str(b)[:40]} {'OK' if a == b else 'DIFF'}")
    await restored.close()
    await admin.execute("drop database restore_check")
    await admin.close()

    await attempt("missing secret", backup_s3_secret_access_key="")
    await attempt("endpoint not https", backup_s3_endpoint="http://fake-s3.invalid")
    await attempt("unreachable", mode="unreachable")
    await attempt("listing refused", mode="list403")
    await attempt("upload refused", mode="put500")
    configure(backup_storage="none")
    jobs = {j.id for j in sched.create_scheduler().get_jobs()}
    configure()
    jobs_on = {j.id for j in sched.create_scheduler().get_jobs()}
    trig = sched.create_scheduler().get_job("offsite_backup").trigger
    lib.out(OUT, f"offsite_backup scheduled when storage=none: {'offsite_backup' in jobs}; when s3: {'offsite_backup' in jobs_on} ({trig})")


asyncio.run(main())

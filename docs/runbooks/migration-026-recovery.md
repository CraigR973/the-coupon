# Forward recovery plan — migration 026 (sweep indexes)

The written plan `/ship-prod` preflight step 1.7 requires before a shipment that
introduces an Alembic revision, and the first one written under the Batch 128
convention. See `docs/runbooks/migrations.md` for what this has to answer and
why it exists at all.

| | |
| --- | --- |
| Revision | `026_sweep_indexes` (`026`, revises `025`) |
| Shipped by | Batch 146 — *The queries that sweep rounds cannot use the indexes that exist* |
| Statements | `CREATE INDEX ix_gameweeks_starts_on ON gameweeks (starts_on)` and `CREATE INDEX ix_picks_gameweek_id ON picks (gameweek_id)` |
| Applied | automatically, by `alembic -c apps/api/alembic.ini upgrade head` in the Railway start command, before uvicorn binds |
| Contracting DDL | **none** — nothing is dropped, renamed, altered or rewritten |

## Why this one is unusually safe

**It moves no data and changes no shape.** Two `CREATE INDEX` statements. No
column is added, dropped, renamed or retyped; no row is touched; no constraint
changes. An index is an access path, and nothing in the application names one.

**The deployed image runs against the new schema without knowing it exists.**
That is the load-bearing property. SQLAlchemy emits explicit column lists and
never references an index by name, so the `025` image reads and writes both
tables exactly as it did — the planner simply has one more option. There is no
version of this change that the running code can notice.

**Measured at production's size on 2026-09-23:** `picks` holds 87 rows in 144 kB
and `gameweeks` holds 24 rows in 40 kB. Both index builds are sub-millisecond.

## The one hazard, and it is not the schema

`CREATE INDEX` without `CONCURRENTLY` takes a `SHARE` lock on the table, which
blocks writes for the duration of the build. At 87 and 24 rows that duration is
under a millisecond and the lock is not worth engineering around. **Revisit at
roughly a million pick rows**, where the build moves into seconds and blocking
writes during a Saturday lock window would be felt; at that point the statement
wants `CONCURRENTLY`, which cannot run inside Alembic's transaction and so needs
its own migration shape.

## Rolling back

**The schema permits a rollback completely. The bookkeeping does not, and that is
the whole of the problem.**

After this lands, `alembic_version` holds `026`. The previous image's history
stops at `025`, so its boot-time `alembic upgrade head` cannot resolve the
revision the database reports and **fails before uvicorn binds**. The container
never becomes healthy. That is what "the migration removes the rollback target"
means here — not that the old code would misbehave against the new schema, but
that it will not start.

So:

> **Fix forward.** Ship a corrected image. There is nothing about this migration
> that a forward fix has to undo, because the indexes cannot be the cause of a
> problem in application behaviour.

If a rollback is genuinely required — a fault in Batch 146's *other* half, the
connection-pool resize, is the only realistic reason — then the database is
already in a state the old image can use, and only the version row is in the way:

1. Confirm the fault is not the indexes. It will not be; they change no results.
2. **With the owner's explicit authorisation**, set the version row back:
   `UPDATE alembic_version SET version_num = '025';`
3. **Leave both indexes in place.** They are invisible to the `025` image, and
   dropping them buys nothing while costing the rebuild on the way forward again.
4. Roll the Railway deployment back as normal and verify `/api/v1/health` reports
   `migration: 025`.

This is the case `docs/runbooks/rollback.md` reserves for a reviewed
migration-specific plan. This is that review, and the answer is: do not roll the
database backward, edit one row of bookkeeping and leave the schema alone.

## What `downgrade()` costs

**Nothing, at any time.** `op.drop_index` on both discards no data — unlike every
migration this project has shipped since `016`, an index carries no information
that is not derivable from the table. The downgrade is genuinely lossless whether
it runs today or in a year. It is still not the intended path, because step 2
above is less work and less risk than a downgrade that has to rebuild the indexes
if the shipment is retried.

## The other half of Batch 146

The same batch changes the SQLAlchemy pool from `10 + 10` to `5 + 5` with a
10-second `pool_timeout`. **That is not part of this migration** and needs no
recovery plan, because it ships and reverts with the image. It is named here only
so that whoever reads this during an incident knows the batch carried two things
and that the pool is the one that can actually cause a fault: the symptom would
be `TimeoutError: QueuePool limit ... reached` in the logs, ten seconds into a
request, under concurrency this deployment has not previously produced.

Backup/restore-point identity: **none**, under the owner's 2026-07-30 deferral.

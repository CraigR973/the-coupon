# Migrations, and why each one costs the rollback

Batch 128. `STATUS.md` has recorded this four separate times as though it were a
one-off. It is structural, it applies to every revision this project will ever
ship, and it is the reason the rule below exists.

## The fact everything here follows from

Production has **no backup, no PITR and no durable dump** — the owner's
2026-07-30 deferral — and `nixpacks.toml` runs `alembic upgrade head` in the
start command, before uvicorn binds. So a shipment that carries a revision
applies it automatically, to a database nothing can restore.

The consequence is not that the migration is risky. It is that **the previous
deployment stops being a rollback target the moment it lands**, because that
image cannot resolve a revision it does not carry. Until the next shipment that
applies nothing, the only way out of a bad deploy is forward.

That is survivable. It is only survivable if the way forward was written down
before the upload rather than worked out during the incident.

## The rule

**A batch that adds an Alembic revision writes
`docs/runbooks/migration-NNN-recovery.md` as part of that batch.** Not at the
shipment, and not afterwards. `scripts/check-migration-recovery.sh` enforces it:
`/ship-prod` step 1.7 runs it, it reads the deployed revision from production's
own `/api/v1/health`, and it refuses the shipment when a revision would be
applied with no plan behind it.

`docs/runbooks/migration-016-recovery.md` is the worked example.

**Revisions 017 to 025 have no file here.** Their plans, where they were written at
all, are sections of `docs/launch/L4_PRODUCTION_INFRASTRUCTURE.md`. They are
already deployed, so neither check fires for them and nothing is being
backfilled; the convention starts from the next revision. If you need one of
them, look there.

A plan answers four questions:

1. **What the statement actually does** — whether it rewrites the table, what it
   locks and for how long, and whether any row is touched.
2. **Whether the currently deployed image can run against the new schema.** This
   is the load-bearing one. If it can, an ordinary Railway rollback is safe and
   the plan should say so in as many words: *roll the deployment back and leave
   the revision in place.*
3. **If it cannot, what to do instead.** Almost always: fix forward and ship a
   corrected image. Name the specific thing that would break.
4. **What a `downgrade()` would cost.** Usually it is lossless only while the new
   table is empty. Say when that stops being true.

## Prefer expand, then contract

Write the revision that a shipment could be rolled back through.

**Expand** — add the new column, table or index, nullable and unused. The
running image does not know about it and is unaffected; SQLAlchemy emits explicit
column lists, so a new column is invisible to an older image, and a new table it
never names cannot affect it. Ship this on its own and the rollback target
survives.

**Migrate** — backfill and start writing the new shape, still tolerating the old.

**Contract** — drop the old column or constraint, in a *later* shipment, once no
image anyone would roll back to depends on it.

The check reports `op.drop_column`, `op.drop_table`, `op.drop_constraint`,
`op.drop_index`, `op.rename_table` and `op.alter_column` found in a revision's
`upgrade()`. It does not refuse them — sometimes contracting is the whole point
of the change — but the plan has to say why that one could not wait for a
shipment that was not also carrying something else.

A `create_table` whose new columns are `NOT NULL` is not contracting and is not
reported: nothing was there to break.

## Where the rule is enforced

| | |
| --- | --- |
| `apps/api/tests/test_migration_recovery_gate.py` | Refuses the **batch**. Add a revision past `025` without its plan and the gate goes red on your own branch. This is the half that matters — it makes the plan get written while somebody still knows why the revision does what it does. |
| `scripts/check-migration-recovery.sh` | Refuses the **shipment**. Reads the deployed revision from production's own `/api/v1/health`, so a stale note about last time cannot satisfy it. `/ship-prod` step 1.7. |

"Usable" has one definition, in `check-migration-recovery.sh --plan-for`, which
the test calls rather than restating. Two copies of that rule would drift, and
the copy that drifted looser would be the one nobody noticed.

The batch half is a test and not a hook in `check-closeout-safety.sh` because
that script is protected: `assert-quality-guardrails.sh` refuses a batch that
edits the machinery judging it. A test is the better place regardless — it runs
on every batch and in CI, not only at close-out.

**An unknown deployed revision exits 2 and is not a pass.** If the check cannot
establish what production is running, the set of revisions a shipment would apply
is unknown — which is not the same as empty. Waving that through would let past
exactly the shipment the check exists to stop.

## What this does not cover

The check proves a plan **exists and is substantive**. It cannot prove the plan is
*right*. That is a reading job, and on a contracting migration it is the owner's.

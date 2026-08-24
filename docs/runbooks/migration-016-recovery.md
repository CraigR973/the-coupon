# Forward recovery plan — migration 016 (nullable `pin_hash`)

The written plan `/ship-prod` preflight step 7 requires before a shipment that
introduces an Alembic revision. Production has **no restore point** (owner's
2026-07-30 deferral) and `nixpacks.toml` applies migrations automatically on
boot, so the change cannot be undone by restoring a backup.

| | |
| --- | --- |
| Revision | `016_nullable_pin_hash` (`016`, revises `015`) |
| Shipped by | Batch 66 — *A member who forgets their PIN has no way back in* |
| Statement | `ALTER TABLE profiles ALTER COLUMN pin_hash DROP NOT NULL` |
| Applied | automatically, by `alembic -c apps/api/alembic.ini upgrade head` in the Railway start command, before uvicorn binds |

## Why this one is low risk

**It moves no data.** Dropping `NOT NULL` is a catalogue change in PostgreSQL:
no table rewrite, no sequential scan, no row touched. It takes a brief
`ACCESS EXCLUSIVE` lock on `profiles`, which holds a handful of rows. Every
existing member keeps their hash.

**It is forward-compatible with the code already in production.** Pre-Batch-66
code reads `pin_hash` and never writes `NULL`; relaxing a constraint does not
change what it reads. That is the load-bearing property of this plan and it is
what makes the ordinary rollback safe:

> **A Railway rollback does not need an `alembic downgrade`.** Roll the API
> deployment back and leave revision 016 in place. The old image runs correctly
> against the relaxed column.

This is the case `docs/runbooks/rollback.md` reserves for a reviewed
migration-specific plan. This is that review, and the answer is: do not roll the
database backward.

## The one hazard, and how to clear it

`NULL` in `pin_hash` means *this member has no credential and cannot sign in
until they set one*. Only an admin PIN reset writes it —
`POST /api/v1/admin/players/{id}/reset-pin` or
`POST /api/v1/leagues/{slug}/members/{id}/reset-pin`.

If a reset is performed **and then** the API is rolled back to pre-Batch-66
code, that member's row holds `NULL` and the old `verify_pin(pin, hashed)` calls
`hashed.encode()` on it. The result is a 500 on **that one member's** login
attempt. Nobody else is affected and nothing else reads the column.

Avoid it: do not use either reset button until the shipment has been confirmed
healthy.

Clear it, if it happens — write any bcrypt hash into the row so the account has
*a* credential again, then have the member change it:

```bash
railway ssh --project e030ebe3-e7fc-43c9-9478-4e80cafaa126 \
  --environment 8f18cb49-5137-4557-900a-031bcab4ac38 \
  --service d59f4f17-3e7d-4b3b-bf40-30620150fa2f \
  'U="${DATABASE_URL/postgresql+asyncpg/postgresql}"; U="${U%%\?*}"; psql "$U" -c "
select id, display_name from profiles where pin_hash is null and deleted_at is null;"'
```

Never pass a production `DATABASE_URL` to `psql` from a local shell: the failure
path prints the whole DSN, password included. The form above derives it inside
the container, so it never reaches the terminal.

## Reversing it deliberately

Only relevant if the feature is being abandoned, not as part of an incident.
`downgrade()` runs `SET NOT NULL`, which **fails while any profile holds
`NULL`** — correctly, because restoring the constraint means deciding what those
members' credential should be. Clear them first (above), then:

```bash
alembic -c apps/api/alembic.ini downgrade 015
```

## Post-deploy check

Confirm the revision landed and no member is stranded:

```bash
railway ssh --project e030ebe3-e7fc-43c9-9478-4e80cafaa126 \
  --environment 8f18cb49-5137-4557-900a-031bcab4ac38 \
  --service d59f4f17-3e7d-4b3b-bf40-30620150fa2f \
  'U="${DATABASE_URL/postgresql+asyncpg/postgresql}"; U="${U%%\?*}"; psql "$U" -c "
select version_num from alembic_version;
select count(*) filter (where pin_hash is null) as awaiting_pin,
       count(*) as profiles
from profiles where deleted_at is null;"'
```

Expect `016` and `awaiting_pin = 0`. A non-zero count immediately after a deploy
means somebody was mid-reset before it, not that the migration did something.

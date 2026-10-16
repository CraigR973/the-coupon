# Forward recovery plan — migration 029 (the Monzo connection and the league's link id)

Batch 208 prepares this plan before its `/ship-prod`, as `docs/runbooks/migrations.md`
requires. Production has no backup or restore point while Batch 95 remains switched
off, so the only way out of a bad deployment is forward.

| | |
| --- | --- |
| Revision | `029_monzo_connection` (`029`, revises `028`) |
| Shipped by | Batch 208 — *Payments through the league's Monzo link never reach the app* |
| Applied | automatically, by the **API's** `alembic upgrade head` in its Railway start command, before uvicorn binds. The payments service never migrates: it refuses to start until the database is at `029` |
| Contracting DDL | **none** — nothing is dropped, renamed, altered or rewritten |

## Statements and locks

Revision `029` does three things, all additive:

1. Adds `leagues.monzo_link_id` (`varchar(64)`, nullable) — a catalogue change only: a
   brief `ACCESS EXCLUSIVE` lock on `leagues`, and no row is rewritten.
2. Adds `ck_leagues_monzo_link_id_shape` (null, or `unipaylink_` followed by letters and
   digits) and the partial unique index `uq_leagues_monzo_link_id`. Both validate every
   existing row under a short lock; every row passes, because no league has a link id yet,
   and `leagues` holds a handful of rows.
3. Creates the empty table `monzo_connections` (at most one row: `singleton` is unique and
   must be true), then enables and forces row-level security on it and revokes the Supabase
   Data API roles (`PUBLIC`, `anon`, `authenticated`), as revisions `027` and `028` did.
   After it, RLS is forced on 25 of 25 tables.

PostgreSQL runs the whole revision in Alembic's transaction, so a failure part-way leaves
the database at `028` with none of it applied.

## The shipment is inert until the owner connects and sets a link id

Nothing writes to `monzo_connections` until the owner opens the payments service's connect
address, and nothing is read from Monzo until a site admin gives a league its
`monzo_link_id` (Batch 210's field, or a `PATCH` of the league). Until then the payments
service serves its health pair and runs an idle five-minute loop, and the API's payments
screen reports no link. Between this shipment and the first connect, the downgrade below
is lossless.

## Compatibility and recovery

The images serving revision `028` never name the new table or column. SQLAlchemy emits
explicit column lists, so their reads and writes run unchanged against the expanded
schema. Nothing the old API image does can be refused by the new constraint, because it
never writes `monzo_link_id`.

A normal Railway rollback of the **API** still **cannot start** after `029` lands. The old
image's boot-time `alembic upgrade head` does not know revision `029` and stops before
uvicorn binds, so the container never becomes healthy. A rollback of the **payments**
service to the Batch 207 image cannot start either: its boot refuses any revision but
`028`. The first response to a faulty Batch 208 deployment is therefore to **fix forward**:
correct the image and ship both services from the same commit, keeping the new table, its
one row and every ledger entry the service wrote.

If only the payments service is at fault, the cheapest stop is to leave it crash-looping
or to remove its deployment: the API, the members' screens and manual entry do not depend
on it, and a missed payment is read by the next healthy catch-up (it reads back to the last
complete read, up to Monzo's 90-day limit).

If the fault is in the API half and an immediate old-image rollback is unavoidable, review
the live schema and migration state first. With a fresh, explicit owner decision,
`alembic_version` may be set back to `028` while leaving the additive schema in place, and
the `028` images redeployed. That bookkeeping edit is **not** authorised by this note or
by `/ship-prod`. While the old payments image runs it reads nothing from Monzo, so link
payments wait in Monzo until the fix ships; tell the owner before choosing this route.
Before a later retry of `029`, account for the objects already created — running the same
`upgrade()` against them would fail. Prefer a reviewed forward repair over this route.

## Downgrade cost

`downgrade()` drops `monzo_connections` — the encrypted tokens, the counting start point
and the link health — then the index, the constraint and `leagues.monzo_link_id`. The
ledger entries the service wrote are untouched, because they live in `ledger_entries`.

After the first connect a downgrade forces the owner to connect again, and resets the
counting start point to that later connect, so payments made in between are read only if
an organiser enters them by hand. **Do not run a downgrade as an automatic rollback.**

# Forward recovery plan — migration 031 (the league's pots and Monzo's approval date)

Batch 214 prepares this plan before its `/ship-prod`, as `docs/runbooks/migrations.md`
requires. Production has no backup or restore point while Batch 95 remains switched
off, so the only way out of a bad deployment is forward.

| | |
| --- | --- |
| Revision | `031_monzo_pots_and_approval` (`031`, revises `030`) |
| Shipped by | Batch 214 — *The owner's own top-ups into the pot are never counted, and Monzo's 90-day approval lapses unannounced* |
| Applied | automatically, by the **API's** `alembic upgrade head` in its Railway start command, before uvicorn binds. The payments service never migrates: it refuses to start until the database is at `031` |
| Contracting DDL | **none** — nothing is dropped, renamed, altered or rewritten |

## Statements and locks

Revision `031` does four things, all additive:

1. Adds a nullable `approved_at timestamp` column to `monzo_connections`. With no default
   it takes a brief `ACCESS EXCLUSIVE` lock on a one-row table and rewrites nothing.
2. Backfills that column on the connection that is already reading: `approved_at =
   webhook_registered_at` where the status is `connected`. The first read after the owner's
   approval registered the webhook in the same moment, so production's row is dated
   16 Oct 2026, 21:32 UTC, and its approval lapses about 14 Jan 2027, 21:32 UTC.
3. Creates the table `monzo_pots` (`league_id` → `leagues`, a unique `pot_ref`,
   `learned_at`, `first_top_up_at`) and the index `ix_monzo_pots_league`. It is new and
   empty, so nothing waits on it.
4. Enables and forces row-level security on `monzo_pots` and revokes the Supabase Data API
   roles (`PUBLIC`, `anon`, `authenticated`), as revisions `027` to `030` did. After it,
   RLS is forced on 27 of 27 tables.

PostgreSQL runs the whole revision in Alembic's transaction, so a failure part-way leaves
the database at `030` with none of it applied.

## What starts happening when it lands

- **The API.** The payments screen's Monzo health carries `approval_lapses_at`, and the
  `payment_notices` job sends the site admins "Monzo needs approving again" once, from
  seven days before the lapse (about 7 Jan 2027).
- **The payments service**, once its `031` image is serving. Its first catch-up reads
  back to the counting start (16 Oct, 21:29 UTC) once, to learn the league's pot from the
  link payments already in Monzo's history. Every one of those is already in the ledger,
  so the read writes nothing new unless Monzo lists a payment the earlier reads missed.
- A top-up from the owner's account into that pot counts only if it was made after the
  pot was learned, so no week the owner recorded by hand is counted again. The first one
  waits in the queue (Batch 213 tells the site admins); once it is assigned, the payer map
  books every later one automatically.
- Until a top-up has been recognised, the payments log carries structure-only lines,
  `monzo pot move not placed: …`, for the pot moves it reads, and at most one
  `monzo link payment names no pot: …` per process. The second means Monzo's link
  payments do not name their pot where the parser looks, and the parser needs a
  follow-up; nothing is counted wrongly meanwhile.

## Compatibility and recovery

The images serving revision `030` never name the new table or column. SQLAlchemy emits
explicit column lists, so their reads and writes of `monzo_connections` run unchanged.

A normal Railway rollback of the **API** still **cannot start** after `031` lands: the old
image's boot-time `alembic upgrade head` does not know revision `031` and stops before
uvicorn binds. A rollback of the **payments** service to the `030` image cannot start
either: its boot refuses any revision but the one it carries. The first response to a
faulty Batch 214 deployment is therefore to **fix forward**: correct the image and ship
both services from the same commit, keeping `monzo_pots` and its rows.

If a top-up is booked wrongly, the ledger entry is permanent: the organiser corrects it
with an adjustment, exactly as for a misassigned link payment, and the fix ships forward.
**Do not delete `monzo_pots` rows to stop the reading.** The service learns the pot again
from the league's next link payment, and from history on its next start, so a delete only
pauses top-ups for a while and moves `learned_at` later. To stop top-ups being read at all,
ship a fix that leaves `pot_top_up` unused.

If the fault is in the API half and an immediate old-image rollback is unavoidable, review
the live schema and migration state first. With a fresh, explicit owner decision,
`alembic_version` may be set back to `030` while leaving the additive schema in place, and
the `030` images of both services redeployed. That bookkeeping edit is **not** authorised
by this note or by `/ship-prod`. Before a later retry of `031`, account for the objects
already created — running the same `upgrade()` against them would fail at its first
`add_column`. Prefer a reviewed forward repair over this route.

## Downgrade cost

`downgrade()` drops `monzo_pots` and then `monzo_connections.approved_at`.

- Dropping `monzo_pots` loses the learned pots and the record of the first recognised
  top-up. The top-ups already booked stay in `ledger_entries`. After a re-upgrade the
  service learns the pots again, later, so top-ups made in between are not counted (it
  fails safe), and the structure-only capture starts logging again.
- Dropping `approved_at` loses the approval date. A re-upgrade backfills it from
  `webhook_registered_at`, which a reconnect by the same owner does not move, so after a
  reconnect the warning would come early, for the old approval.

**Do not run a downgrade as an automatic rollback.**

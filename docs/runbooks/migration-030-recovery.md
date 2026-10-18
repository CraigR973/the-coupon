# Forward recovery plan — migration 030 (payment notices)

Batch 213 prepares this plan before its `/ship-prod`, as `docs/runbooks/migrations.md`
requires. Production has no backup or restore point while Batch 95 remains switched
off, so the only way out of a bad deployment is forward.

| | |
| --- | --- |
| Revision | `030_payment_notices` (`030`, revises `029`) |
| Shipped by | Batch 213 — *The organiser learns of a queued payment or a broken Monzo link only by looking* |
| Applied | automatically, by the **API's** `alembic upgrade head` in its Railway start command, before uvicorn binds. The payments service never migrates: it refuses to start until the database is at `030` |
| Contracting DDL | **none** — nothing is dropped, renamed, altered or rewritten |

## Statements and locks

Revision `030` does four things, all additive:

1. Adds three `boolean NOT NULL DEFAULT false` mute columns to `notification_preferences`
   (`mute_payment_queue`, `mute_monzo_link`, `mute_payments`), as revision `027` did. Each
   takes a brief `ACCESS EXCLUSIVE` lock; PostgreSQL keeps a constant default in the
   catalogue, so no existing row is rewritten.
2. Creates the table `notification_sends` with the unique pair `(kind, subject)`
   (`uq_notification_sends_kind_subject`). It is new, so nothing waits on it.
3. Seeds it with one `payment_queued` row for every link payment already in
   `ledger_entries` (`kind = 'payment'` with a Monzo transaction id), and one
   `payment_recorded` row for each of those that already has a member. This reads
   `ledger_entries` under an ordinary `SELECT` and writes nothing to it; the ledger holds
   a few dozen rows, so it is instant. Its purpose is that the first scheduler run tells
   nobody about payments that arrived before the shipment.
4. Enables and forces row-level security on `notification_sends` and revokes the Supabase
   Data API roles (`PUBLIC`, `anon`, `authenticated`), as revisions `027` to `029` did.
   After it, RLS is forced on 26 of 26 tables.

PostgreSQL runs the whole revision in Alembic's transaction, so a failure part-way leaves
the database at `029` with none of it applied.

## What starts happening when it lands

The API's new `payment_notices` job runs every ten minutes (:07, :17 … :57 UTC). It reads
the ledger and the Monzo connection's health columns, claims each notice in
`notification_sends`, writes the inbox rows and commits, then sends the pushes. The first
run after the shipment finds only what arrived after the migration, plus at most one
"Monzo needs connecting again" or "Monzo has stopped reading" notice if the link is down
at that moment.

## Compatibility and recovery

The images serving revision `029` never name the new table or columns. SQLAlchemy emits
explicit column lists, so their reads and writes of `notification_preferences` run
unchanged: an insert from the old image leaves the new columns at their default.

A normal Railway rollback of the **API** still **cannot start** after `030` lands. The old
image's boot-time `alembic upgrade head` does not know revision `030` and stops before
uvicorn binds. A rollback of the **payments** service to the `029` image cannot start
either: its boot refuses any revision but the one it carries. The first response to a
faulty Batch 213 deployment is therefore to **fix forward**: correct the image and ship
both services from the same commit, keeping `notification_sends` and its rows.

**Do not empty `notification_sends` to "retry" a notice.** Every row in it stands for a
notice already sent, or for a payment that arrived before the shipment; deleting rows
re-sends them all within ten minutes, up to the job's seven-day look-back.

If only the notices are at fault — wrong copy, a wrong audience, too many — the cheapest
stop is to ship a fix that leaves the job unregistered. Nothing else reads the new table,
and the payments screen, picks and the ledger do not depend on it. Muting is also
immediate per person: Settings → Notification kinds.

If the fault is in the API half and an immediate old-image rollback is unavoidable, review
the live schema and migration state first. With a fresh, explicit owner decision,
`alembic_version` may be set back to `029` while leaving the additive schema in place, and
the `029` images of both services redeployed. That bookkeeping edit is **not** authorised
by this note or by `/ship-prod`. Before a later retry of `030`, account for the objects
already created — running the same `upgrade()` against them would fail at its first
`add_column`. (Its seed alone is safe to repeat: it skips pairs already present.) Prefer a
reviewed forward repair over this route.

## Downgrade cost

`downgrade()` drops `notification_sends`, then the three mute columns. Before the first
member mutes one of the new categories, the columns are lossless to drop. The table is
never lossless after the first run: without it, the next upgrade's seed marks only the
ledger as told, so any Monzo-link outage notice would be sent again and a recovery notice
could be lost. Mutes set in the meantime are erased. **Do not run a downgrade as an
automatic rollback.**

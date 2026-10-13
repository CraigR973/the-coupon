# Forward recovery plan — migration 028 (pay to pick: fee, ledger, payer map)

Batch 205 prepares this plan before its `/ship-prod`, as `docs/runbooks/migrations.md`
requires. Production has no backup or restore point while Batch 95 remains switched
off, so the only way out of a bad deployment is forward.

| | |
| --- | --- |
| Revision | `028_pay_to_pick_ledger` (`028`, revises `027`) |
| Shipped by | Batch 205 — *A member can pick in a league that charges a fee without having paid* |
| Applied | automatically, by `alembic upgrade head` in the Railway start command, before uvicorn binds |
| Contracting DDL | **none** — nothing is dropped, renamed, altered or rewritten |

## Statements and locks

Revision `028` does five things, all additive:

1. Adds `leagues.entry_fee_pence` (`integer`, nullable) and `leagues.payment_link_url`
   (`varchar(500)`, nullable). Nullable columns with no default are a catalogue change
   only: a brief `ACCESS EXCLUSIVE` lock on `leagues`, and no row is rewritten.
2. Adds two check constraints to `leagues`: `ck_leagues_entry_fee_positive` (a fee is
   positive) and `ck_leagues_entry_fee_private` (a league with a fee is `private`).
   Adding a check constraint validates every existing row under the same short lock.
   Every row passes, because no league has a fee yet; `leagues` holds a handful of rows.
3. Adds `league_memberships.adult_confirmed_at` (`timestamp`, nullable) — catalogue only.
4. Creates two empty tables, `ledger_entries` and `payer_mappings`, with their check
   constraints, unique indexes and foreign keys to `leagues`, `profiles` and `gameweeks`.
   Creating a foreign key takes a brief `SHARE ROW EXCLUSIVE` lock on the table it
   references; the new tables have no rows, so nothing is validated at length.
5. Enables and forces row-level security on both new tables and revokes the Supabase
   Data API roles (`PUBLIC`, `anon`, `authenticated`), as revision `027` did for
   `member_notifications`. After it, RLS is forced on 24 of 24 tables.

PostgreSQL runs the whole revision in Alembic's transaction, so a failure part-way leaves
the database at `027` with none of it applied.

## The shipment is inert until the owner sets a fee

Nothing writes to the new tables, and no member sees any difference, until a site admin
sets `entry_fee_pence` on a league (ADR 0009's launch step 6). Every new code path —
dues at an opening, the charge on joining, the paid-up check in `submit_pick`, the fee
in the round payload, the reminder copy — returns before its first query for a league
without a fee. Between this shipment and the owner setting 2-1 Hibs' fee, the ledger is
empty and the downgrade below is lossless.

## Compatibility and recovery

The image serving revision `027` (`a2557bd` as of 10 Oct) never names the new tables or
columns. SQLAlchemy emits explicit column lists, so its reads and writes run unchanged
against the expanded schema. One write can now be refused that was not before: once a
league has a fee, the old image's league edit cannot make it public, because
`ck_leagues_entry_fee_private` rejects the row. That is a refusal, not a corruption.

A normal Railway rollback still **cannot start** after `028` lands. The old image's
boot-time `alembic upgrade head` does not know revision `028` and stops before uvicorn
binds, so the container never becomes healthy. The first response to a faulty Batch 205
deployment is therefore to **fix forward**: correct the image and ship it, keeping the
new tables and every row in them.

If the fault is solely in the Batch 205 application and an immediate old-image rollback
is unavoidable, review the live schema and migration state first. With a fresh, explicit
owner decision, `alembic_version` may be set back to `027` while leaving the additive
schema in place, and the `027` image redeployed. That bookkeeping edit is **not**
authorised by this note or by `/ship-prod`. While the old image runs it neither records
dues nor refuses unpaid picks, so a league with a fee is in effect free until the fix
ships; tell the owner before choosing this route. Before a later retry of `028`, account
for the objects already created — running the same `upgrade()` against them would fail.
Prefer a reviewed forward repair over this route.

## Downgrade cost

`downgrade()` drops `payer_mappings` and `ledger_entries` — every due, payment,
reversal, cash-out and adjustment, and every remembered payer — then the 18+
confirmations and both league columns, so every league's fee and payment link go too.

It is lossless only until the first fee is set or the first entry is written. After
that it permanently erases the league's record of who owed and who paid, which nothing
else holds: the bank statement shows money in, not which round it paid for. **Do not run
a downgrade as an automatic rollback**, and never after the owner has begun recording
payments.

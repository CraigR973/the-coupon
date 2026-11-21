# Forward recovery — migration 032, inactive two-game storage

13 Nov 2026 · local rehearsal only. Production migration is not authorised.

Revision 032 follows 031. The API normally migrates on boot; payments never
migrates and requires the image's exact head. An already-running 031 payments
reader can overlap this additive upgrade; a restarted 031 image cannot pass its
revision check. Readiness failure does not stop an existing reader.

## Schema and locks

The revision adds `gameweeks.format`, defaulting every historical/old-writer row
to `legacy`, plus its ownership key and check. PostgreSQL takes a brief DDL lock;
Alembic's existing five-second lock timeout and transactional DDL remain intact.
No historical row, pick, result, price, payment, reversal or notification is
copied, deleted, relabelled or repriced.

Fifteen initially empty tables hold rollout, game children, fixture memberships,
separate group/fantasy picks, membership intervals, weekly fee provenance,
provider reservations/refusals/control/snapshots/work, operations, events and
confirmed breaks. Foreign keys are indexed and enforce ownership. New tables
have forced RLS and no PUBLIC/anon/authenticated grants; trigger functions are
security invokers with fixed search paths and revoked public execution.
The [Supabase security guidance](https://supabase.com/docs/guides/api/securing-your-api)
distinguishes grants from RLS; both are checked locally.

Triggers make format/announced identity immutable, reject legacy picks/fixture
memberships on new parents, enforce fixed child windows and eligible fixtures,
and preserve owed-fee/member provenance and committed provider reservations.
Only ledger rows referenced by new weekly obligations gain the additional
immutability guard; legacy history and queued-payment assignment keep working.

The installation gate defaults false. Migration creates no rollout, new-format
week, child, due, event or provider job. Existing legacy entry/settlement/payment
behaviour remains supported. Activation requires a separately approved untouched
future week, successfully shipped API/payments, and live acceptance evidence.

## Recovery decision

Do not roll the image back to 031 after this migration. The previous API cannot
resolve 032 and the previous payments image refuses the revision on restart.
Do not edit `alembic_version` to make an old image boot. Never drop provider
reservations, cooldowns, fee provenance or accepted picks to recover service.
`downgrade()` deliberately refuses: a destructive schema rollback would lose
accepted work and could mint fresh quota or duplicate fees.

For application failure, keep the schema at 032, stop new entry/opening through
the approved league suspension procedure, preserve billing/settlement/history,
and deploy a reviewed forward-compatible repair under separate release approval.
Suspension does not waive weekly dues or change parent format.
For DDL failure, transactional rollback leaves 031 intact; diagnose the failed
statement/lock, correct forward, then rehearse the entire upgrade again.

## Before activation: the lossless undo

Owner decision, 19 Nov 2026 (relayed verbatim: "yes proceed"). Until the format is
switched on, every table 032 created is empty and every week is legacy, so none of
the work the rules above protect exists yet. In that window only,
`migration-032-undo.sql` reverses 032 exactly and keeps every legacy row written
since it landed — a backup restore would lose those.

- **Guards.** It refuses unless the revision is 032, all fifteen two-game tables are
  empty and no week is non-legacy. One transaction, five-second lock timeout, no
  CASCADE, so an unexpected dependency fails rather than disappearing.
- **Order.** Stop `api`, then `payments` (`railway down` with explicit project,
  environment and service). Run the script with `psql -X -v ON_ERROR_STOP=1 -f`,
  over verified TLS (`backup-restore.md`). Roll both services back to their 031
  deployments. Check `/health` and `/health/ready` report 031, rerun the RLS and grant
  audit, and compare row counts with those taken just before.
- **The revision tells the truth.** It records 031 only after removing everything 032
  added, so the rule against editing `alembic_version` to make an old image boot
  still stands.
- **Afterwards it is forward-only.** Once any two-game table holds a row — a rollout,
  a due, a provider attempt — the script refuses and the rules above apply.

Tested by `tests/test_migration_032.py`: after the undo the schema equals a fresh 031
schema as `pg_dump` prints it, later legacy writes survive and 032 re-applies; a
refusal changes nothing. Rehearsed 19 Nov on a Supabase-shaped PostgreSQL 17 copy (anon
and authenticated roles, auth policies, forced RLS): 0.1 s, schema identical to an
untouched 031 copy line for line (742 lines), all 26 legacy tables kept the post-032
writes, the 031 API booted on it, and one rollout row made it refuse. On the real
archive (21 Nov 2026, 27 tables, 17,780 rows): 032 applied in 1.9–4.7 s, with every
legacy table identical and the fifteen new ones empty; the undo took 0.1 s, left the
schema identical to a fresh restore (790 lines) and kept the legacy writes made at 032
in all 26 legacy tables; the 031 API booted on it; one rollout row made it refuse
(exit 3) and change nothing.

## Local rehearsal and required release evidence

Use synthetic scratch databases only. Run the dedicated 032 migration/storage
tests and the unmodified full `scripts/ci-local.sh` gate. The tests must compare
populated legacy UUIDs/results/prices/points, dues/reversals, matched/queued
payments and notification claims before/after; exercise old SQL read/write and
queued assignment; check new constraints/RLS/grants; preserve committed budget,
snapshot and cursor state across fresh sessions and forward repair/restore.
Record actual results in the overnight report; this document is not proof that
an unrun test passed.

Before any production migration, separately authorise and test a fresh recovery
point against the actual current production revision and affected data. A local
synthetic dump/restore is no production recovery point. Ship the API first,
payments second at the same SHA/head with the feature off; verify readiness,
RLS and legacy behaviour before web release. No bank/provider probe or natural
payment/notification receipt is supplied by these synthetic rehearsals.

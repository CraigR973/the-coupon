# Backfill note — 2-1 Hibs, round numbers and three display names

Batch 74, from the owner's first and fourth points on 2026-08-25. Two unrelated
corrections in one run, because both rewrite a name people have already used and neither
has a screen in the product that could do it.

The run is `apps/api/src/backfill_names_and_numbers.py`.

```bash
python -m src.backfill_names_and_numbers --dry-run
```

## What changes

| Round (`starts_on`) | Was | Becomes |
| --- | --- | --- |
| Sat 8 Aug 2026 | unnumbered | Gameweek 1 |
| Sat 15 Aug 2026 | unnumbered | Gameweek 2 |
| Sat 22 Aug 2026 | **Gameweek 1** | Gameweek 3 |
| Sat 29 Aug 2026 | Gameweek 2 | Gameweek 4 |

| Profile | Was | Becomes |
| --- | --- | --- |
| — | Craig | Craig Robinson |
| — | Birch | Marc Birch |
| — | Lewis | Lewis Steele |

## The renumbering reverses a decision, deliberately

Batch 68 wrote the 8 and 15 August rounds in with `number = NULL` and said why, at
`backfill_august_2026.py:459`: 22 August was "Gameweek 1" and members had been told so, so
numbering the earlier rounds 3 and 4 would put a later number on an earlier date, and
renumbering 22 August would rewrite a name people had already used.

**The owner's call on 2026-08-25 is to rewrite it.** The season should read 1-4 from
8 August. That reasoning was not wrong; it was a judgement about which cost was worse, and
the owner has now made it the other way.

No code follows. `next_gameweek_number` is one past the season *maximum*, so once these
four read 1-4 the next discovered round takes 5 unaided — and before the run it would have
handed out 3, a number 22 August was already using. There is a test for exactly that.

## The rename changes how three people sign in

`profiles.display_name` is globally unique **and is the login identifier**
(`routers/auth.py:228` matches it exactly). The owner chose it over
`league_memberships.display_name_override`, which is per-league and cosmetic and would
have changed nothing about signing in.

Consequences, written down here because they are the reason this is not a cosmetic change:

- **Nobody is signed out.** The JWT subject is the player id, so existing sessions
  continue.
- **The next sign-in needs the new name**, and so does any forgotten-PIN request
  (`auth.py:695`). **The three must be told.** Nothing in the product tells them.
- **The freed names become registrable by anyone.** This is *worse* than deleting a
  member: `auth.py:436`'s case-insensitive reservation deliberately includes soft-deleted
  rows, so a departed member keeps their name — but a renamed one releases it, because
  afterwards no row holds it at all. If "Craig" matters, somebody should take it.
- **`invites.display_name_hint` and the audit payloads keep the old strings**, correctly.
  Both are records of what was true when written, not pointers to a profile.

## What was checked

**Verified read-only against production on 2026-08-26**, over a direct `asyncpg`
connection to `db.pugujiiojitstkilphrz.supabase.co`. Nothing was written.

```
2026-08-08  number=None  status=settled
2026-08-15  number=None  status=settled
2026-08-22  number=1     status=settled
2026-08-29  number=2     status=open
```

All four rounds exist, so nothing aborts on a missing Saturday. And each of the three
target names is free while each old name is held exactly once — checked
case-insensitively and including soft-deleted rows, the same test `auth.py:436` applies:

| Old name | Held | Target | Held | |
| --- | --- | --- | --- | --- |
| `Craig` | 1 | `Craig Robinson` | 0 | OK |
| `Birch` | 1 | `Marc Birch` | 0 | OK |
| `Lewis` | 1 | `Lewis Steele` | 0 | OK |

So `--apply` will resolve cleanly whenever it is run. **It has not been run. Nothing in
production has changed.**

### A wrong turn worth recording

An earlier draft of this note said the check could not be performed because "the Supabase
MCP timed out on every query, including `select 1`", and reasoned that production must
still be healthy because the deployed API was answering.

The reasoning was sound and the premise was wrong. **The Supabase MCP is not attached to
this project at all** — `docs/launch/L0_PROJECT_IDENTITY.md` lists it as pointing at
`wc2026-predictor`, explicitly excluded, and states The Coupon's production database "is
never attached to MCP". Those timeouts were a different product's database. The Coupon's
was reachable the whole time, directly, from the `ci-local` venv.

The lesson is not "the MCP was down". It is that a tool answering slowly looks identical
to a tool pointed somewhere else, and only checking *which database* distinguishes them.

## Before applying

1. `--dry-run` against production and read the plan. It prints both halves, and for each
   rename it prints the name being freed.
2. Check the four rounds listed are the four expected — a missing Saturday aborts the run
   by design, naming the date.
3. Apply, then tell Craig, Marc and Lewis their new sign-in names.

## How it fails

Every round and every profile must resolve to exactly one row or nothing is written. The
cases with tests behind them:

- a Saturday with no round → raises, naming the date;
- a target name held by another profile, in any case → raises, and the renumbering does
  not land either;
- an old name that matches nothing and has not already been changed → raises;
- run twice → the second run is a no-op, because each rename resolves through the new name
  as well as the old one.

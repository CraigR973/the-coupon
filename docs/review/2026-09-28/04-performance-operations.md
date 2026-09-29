# 04 — Performance and operations

Status: **in progress** (sections marked *pending* are not yet measured).

## Method

The API was measured in process against a scratch PostgreSQL (the shared harness's
`stack.py --name perf --no-api`, migration 026) with a statement listener on the app's own
engine, at the two data shapes the 2026-09-13 pass used, rebuilt from its description
because its seeding scripts were lost (`notes/04-perf/seed_shapes.py`):

- **production shape** — 5 leagues (largest 12 members), 6 settled + 1 open round each,
  1,174 pooled fixtures; the open round holds 264 fixtures across 23 competitions
  (production's largest measured round); one league on a Friday window, so two windows.
- **stress shape** — that plus a 50-member league with 40 settled rounds (34 in 2025/26,
  6 in 2026/27) at 200 fixtures each and one pick per member per round: 76 rounds,
  8,364 fixtures, 2,295 picks. Season calendars exist for both seasons (production's
  table is empty today, so production pays slightly less for labels than measured).

Statements are split at the moment the final response body leaves the app, so the
Batch 162 background fan-out is counted apart from the member's request. Odds come from
an in-process fake that prices every fixture in both markets — the fully-priced upper
bound for payload size. `notes/04-perf/measure_api.py` → `api-production.json`,
`api-stress.json`, and the SQL of every request in `api-*-sql.txt`.

The machine is shared with other passes; `uptime` is recorded beside every timing, and
**counts, plans and bytes are the evidence**. Production was touched only for response
headers on `GET /api/v1/health`.

## The numbers

Production shape → stress shape. "stmts" is SQL statements on the member's request.

| endpoint | stmts 13 Sep | stmts now | bytes identity → gzip |
| --- | --- | --- | --- |
| home summary (1 league, 3 leagues) | 15 → 15 | **13 → 13** | 2.0 KB; 5.5 KB → 1.5 KB |
| current round / slate | 12 → 12 | **56 → 66** | 299 KB → **15.2 KB** (264 fully priced) |
| combined coupon | 6 | 6 → 6 | 3.2 KB; 11.7 KB → 2.4 KB (50 legs) |
| standings (with and without season) | 5 | 5 → 5 | 10.4 KB → 1.2 KB; 43 KB → 3.7 KB |
| results | 7 | 7 → 7 | 1.3 KB; **500 at stress** (PERF-19) |
| rounds list | 8 | 8 → 8 | 1.7 KB; 10 KB → 1.9 KB |
| account export (new) | — | 6 → 6 | 6.1 KB → 1.0 KB; 11 KB → 1.7 KB |
| pick submit | 12 → 12 | **11** + 3 after the response | 0.5 KB |

Every count is identical at both shapes **except the slate**, which grows with the
number of competitions on the card rather than with data volume (PERF-18). The home
summary at the stress shape returned **500** for a member of the 50-member league
(PERF-19).

## Prior findings

*Partial — rows are added as each is re-driven.*

| id | batch | verdict | evidence |
| --- | --- | --- | --- |
| PERF-01 + OPS-16 | 144 | **held** | home summary 13 statements at both shapes and for 1 or 3 leagues (was 15); one `SELECT DISTINCT gameweeks.starts_on` projection, not whole rounds (`api-*-sql.txt`) |
| PERF-04 | 146 (migration 026) | **held** | the SQL the app actually runs, captured from `retire_stranded_rounds` and the settle sweep at the stress shape and explained: retirement's pick-existence check is an `Index Only Scan using ix_picks_gameweek_id`, the settle sweep's pending-pick read a `Bitmap Index Scan on ix_picks_gameweek_id` — both by the planner's own choice. The 76-row `gameweeks` table is still sequentially scanned, correctly at one page; with seq scans disabled both reads take `ix_gameweeks_starts_on` (`explain-stress.txt`) |
| PERF-05 | 146 | **held** | pool is 5 + 5 with a 10 s `pool_timeout` (`database.py`), down from 10 + 10 — but see PERF-20 for what now holds a connection |
| PERF-03 | 145 | **held locally; not checkable in production read-only** | 264-fixture slate 299,134 B → 15,202 B with `content-encoding: gzip`, `vary: Accept-Encoding`; responses under 4 KB deliberately uncompressed. Production's only public API responses (`/health`, 82 B) sit below the floor, so no header could prove it (`prod-health-headers.txt`) |

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| PERF-19 | HIGH | live | verified | A league of 40-50 members breaks its home screen and results once the combined odds pass about 10^26 |
| PERF-18 | MED | live | verified | The slate makes two queries per competition on the card — 56 statements at production's 23 competitions |

## PERF-19 · HIGH · live · verified — the combined odds overflow in large leagues

`combined_odds` (`services/coupon.py:30-40`) multiplies every leg and quantizes to two
decimal places under Python's default 28-digit decimal context. A product at or above
about 10^26 cannot be represented to 2 dp there and raises `decimal.InvalidOperation`,
which is uncaught on all four call sites: the home summary (`routers/me.py:469`, `:552`),
the combined coupon (`services/coupon.py:179`) and the results screen
(`services/scoring.py:773`).

Measured with the app's own function (`notes/04-perf/combined-odds-limit.txt`): 20 legs
fail only at 19.96 each, but **30 legs fail at an average leg of 7.36, 40 at 4.47 and 50
at 3.32**. At the stress shape (50 members, prices 1.30-9.00) the home summary and the
results screen both returned **500** for members of that league; the 12-member leagues
beside it were unaffected (`api-stress.json`).

Tried to disprove: no decimal context is set anywhere in `apps/api/src` (grep for
`getcontext`/`localcontext` is empty); the threshold is a property of the arithmetic,
not the seed; `max_members` accepts up to 50 (`routers/leagues.py`); and the game scores
`round(odds × 10)`, so members are rewarded for longer prices, which pushes the average
leg up rather than down. Not live pressure today — production has one league of 13 — but
nothing refuses the league size that triggers it.

**Member impact:** in a big league, the home screen fails for every member (the summary
is one call across all their leagues) and the results history fails for the league once
any settled round's accumulator passes the limit — permanently, since history does not
change.

**Fix:** quantize inside `decimal.localcontext()` with enough precision (or cap the
displayed price and flag it), and add a 50-leg test at realistic prices.

## PERF-18 · MED · live · verified — the slate queries per competition

The round screen's statement count is **10 + 2 × competitions on the card**: 56 at
production's 23 competitions, 66 at 28. `fixture_context` (`services/football_data.py:923-990`)
calls `resolve_names` once per competition (`:950`), and each call reads the alias table
and then the competition's teams (`services/team_matching.py:263`, `:284`). Its docstring
says "three queries for a slate of any size". The code is unchanged since Batch 16; the
2026-09-13 pass measured 12 because its round spanned one competition, so **its "no N+1
anywhere" was wrong for this screen** — the counts did not vary with the one factor that
drives them.

Bounded — at most the 41 played competitions, 92 statements — but these are serial round
trips on the most-used screen on a Saturday morning: at a 5-10 ms Railway→Supabase round
trip (not measured; production cannot be probed read-only) the 46 extra statements are
roughly 0.2-0.5 s per card load.

**Member impact:** the pick screen is slower than it needs to be, and slower the wider
the card.

**Fix:** resolve every competition's names in two queries (`IN` over competition ids),
as the docstring already claims.

## Checked and found nothing material

*pending*

## Proposed batches

*pending*

## Owner decisions

*pending*

## Doc corrections

*pending*

## What this pass did not do

*pending*

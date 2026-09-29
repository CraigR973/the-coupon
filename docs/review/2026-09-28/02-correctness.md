# 02 — Correctness: does it work as expected

Judged against the product contract at the top of `docs/BUILD_PLAN.md` and the
acceptance text of Batches 95, 115 and 120-168, not against intuition. Written
incrementally while the pass ran (two usage-limit interruptions); anything not yet
re-driven is marked so.

## Method

A scratch PostgreSQL (pgserver, migration 026) held by the shared harness
(`notes/harness/stack.py --name corr --no-api`), and the seeded test server run as
`notes/02-correctness/corr_server.py` on port 8120. That server is
`tests.e2e_server:app` with its provider overrides **removed**, so every request goes
through the production path — `odds_session` → `CachingOddsProvider` (60-second pick
tier, plan counter, pick reserve) — onto a deterministic, counting FakeBetfair
(`richfake.py`: 50 fixtures across Friday 19:45, Saturday 15:00 and the Sunday the
clocks go back, three competitions, both markets). Pushes are captured at the
`webpush` call (every profile holds a fake subscription), so the mute and quiet-hours
gates still run. `ODDS_PROVIDER=fake` and `FOOTBALL_DATA_PROVIDER=none` throughout; no
live provider and nothing in production was touched.

Four leagues were seeded in process (`seed_two_leagues.py`) with deliberately
different configurations — **L1** on the defaults (Saturday 15:00, lock 30,
`MATCH_ODDS` only, `selection` scope); **L2** Friday 19:00-22:00, lock 60, both markets,
a two-competition subset, `fixture` scope; **L3/L4** twelve-member race leagues in
`selection` and `fixture` scope — with members on London, New York, Sydney and UTC
profiles and two members in both L1 and L2. Rounds were created by the scheduler's own
`run_discover_fixtures`; lock, settle, reminders and backup were advanced by calling
the scheduler's job functions against the scratch database. Scripts and raw output are
in `notes/02-correctness/` (`out/*.txt`).

## Prior findings

| id | batch | status | evidence |
| --- | --- | --- | --- |
| CORR-08 | 120 | **held** | 4 runs × 12 simultaneous HTTP submissions for one selection (2 in `selection` scope, 2 in `fixture` scope): each run exactly one 201 and eleven 409 (`SELECTION_TAKEN` / `FIXTURE_TAKEN`), zero 500s, `Access-Control-Allow-Origin` present on every 409; no 500 anywhere in the API log (`out/race.txt`) |
| CORR-14 | 130 | **partial** | Held for the path Batch 130 wired: in L1, four of five picked and the fifth *left* → one completion row with an empty picker name, "4/4 picked — all picks are in" pushed to the four remaining members; a later pick move by Bob wrote no second row and was announced as an ordinary move. **Not fixed on the self-deletion path Batch 136 added two days later** — see CORR-19 (`out/completion.txt`) |
| CORR-09 | 121 | **held**, residual in CORR-20 | Saturday→Friday window edit on Wed 30 Sep, driven over HTTP with discovery re-run: the stray Saturday round with **no** pick was retired (L5, Batch 112's rule intact); the stray holding Bob's pick was kept, and both settle passes refused it with `same-football-week settlement refused … reason=undeclared_same_week_round` while the Friday round settled — one scoring round, standings sum only Friday (`out/window.txt`). But the kept stray **still accepted a new pick** after the edit (Carol, 201) — CORR-20 |
| CORR-13 | 121 | **not fixed** | The same reproduction: `GET /leagues/l6-sat-picked/gameweeks` labels both the Friday round and the stray Saturday round `season_week = '1'`, so the member still sees two "Gameweek 1" entries in one football week. Batch 121's verification line asked for "exactly one scoring round and one label"; the settle guard delivered the first half only (`out/window.txt`) |

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| CORR-19 | MED | live | verified | A member deleting their own account completes the round silently, and the next pick change is announced as the completing pick |
| CORR-20 | MED | live | verified | A round the settle guard will never settle is still offered for picks, which then stay pending for ever |

## CORR-19 · MED · live · verified — self-deletion reopens CORR-14

Batch 130 made a round re-evaluate completion whenever the roster shrinks — leaving,
being removed, and a site admin deleting an account all call
`settle_completion_after_roster_change` after their commit. Batch 136's self-service
deletion (`POST /api/v1/me/delete`, `routers/me.py:623-665`) sets the profile inactive
and deleted exactly as the site-admin delete does, which drops the member out of
`round_progress`'s count — but never calls that hook.

Reproduction (`notes/02-correctness/completion.py`, `out/completion.txt`), L3 with
twelve active members: R01-R11 pick; R12 deletes his own account (204). The league now
has 11 active members and 11 picks, and `gameweek_completions` is **empty** and **zero**
pushes went out. R05 then moves his pick: a completion row is written naming R05, and
all eleven members receive "R05 picked No — not both score (Millwall v Watford) @ 1.65 ·
11/11 picked — all picks are in". That is CORR-14's defect exactly — silent completion,
then the wrong member credited — on the one roster path added after Batch 130.

**Member impact:** when the last outstanding member deletes their account, the league is
never told the coupon is complete, and when anyone next touches a pick it is announced
as that member completing it.

**Fix:** call `settle_completion_after_roster_change` for each of the member's leagues
after `delete_my_account` commits (read the league ids before the erasure, as the
site-admin delete does), plus a test mirroring Batch 130's leave test for self-deletion.
API-carrying.

## CORR-20 · MED · live · verified — a round that can never settle still takes picks

Batch 121 answered CORR-09 with a settle-time guard (`scoring._same_week_round_may_settle`):
in a league's Wednesday-to-Tuesday week, an undeclared round that is not on the league's
current weekday is refused, and so is the league's own round if an undeclared sibling
has already settled. The guard is right about scoring, but nothing on the *offering*
side knows about it — discovery still creates the round, the round list still shows it,
and the pick path (`routers/picks.py:_round_playing` + `pick_refusal`) checks only status
and time. Two reachable shapes, both reproduced (`notes/02-correctness/window_change.py`,
`out/window.txt`):

1. **The kept stray keeps taking picks.** L6 on Saturday defaults; Bob picks Saturday 3
   Oct; the admin moves the league to Friday 19:00 on Wednesday; discovery creates Friday
   2 Oct and keeps the Saturday round because it holds a pick. Carol then claims a
   selection on that Saturday round — **201**. At settlement Friday settles and the
   Saturday round is refused on both sweeps: Bob's and Carol's picks stay `pending`, the
   round stays `locked`, and an error is logged every evening.
2. **The league's own new round after its week already settled.** L7 on Friday
   19:00; its Friday 2 Oct round settles (Carol 19 points); that night the admin moves it
   to Saturday 15:00; the next discovery creates Saturday 3 Oct in the same football
   week, labelled `1` like the settled Friday round, open for picks. Bob and Carol both
   pick (201, 201). Settlement refuses it with `reason=undeclared_sibling_already_settled`
   on every sweep — for ever. Neither the admin's manual settle (which calls the same
   `settle_gameweek`) nor pick correction (settled picks only) can move it.

No member is told anything: the picks read as pending indefinitely, and the table simply
never moves for that week.

**Disproof attempted.** Retirement cannot help — the stray in (1) holds a pick and the
round in (2) is on the league's cadence, so both are legitimate by
`retire_stranded_rounds`'s rules. Neither `sync_slate` nor `discover_fixtures` consults
the settle guard's rule, and no refusal on the pick path mentions it. Rated MED rather
than HIGH because standings stay internally consistent (one scoring round per league per
week, the guard's purpose) and nobody gains points others could not; the harm is picks
made in good faith that silently never count, plus a round stuck `locked` for ever.

**Member impact:** after a mid-season window change, members can pick on a round that
will never settle, and their picks sit "pending" indefinitely with no explanation.

**Fix:** apply the guard's rule where rounds are offered: `sync_slate` should not create a
round in a football week where the league already holds a settled round (or a kept
stray), and the pick path should refuse (`ROUND_NOT_SCORING`, 409) a round
`_same_week_round_may_settle` would refuse. Give the operator an explicit way to void a
refused round's picks rather than leaving them pending. Travels with CORR-13's label fix.
API-carrying.

## Checked and found nothing material

## Proposed batches

## Owner decisions

## Doc corrections

## What this pass did not do

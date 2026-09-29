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
| CORR-11 | 132 | **held** | `POST /admin/calendar/extra-weeks` as the site admin: 26 Sep and 23 Sep → 422 `EXTRA_WEEK_IN_THE_PAST`; Mon 5 Oct, in the football week whose rounds have settled → 409 `EXTRA_WEEK_LOCKED`; Wed 14 Oct → 200, then withdrawn 200 (`out/calendar.txt`). A future week whose round is open *with picks* can still be relabelled — within the batch's stated scope |
| CORR-12 | 132 | **held** | In process on an empty season 2027 (rolled back): a Friday league's 13 Aug 2027 round discovered first set the anchor to 14 Aug; the Saturday league's 7 Aug round then pulled it back to 7 Aug, labels `1` / `2`. Reverse order: anchor 7 Aug, same labels |
| CORR-16 | accepted | **still true, still harmless** | Wed 30 Jun 2027 labels `40` on the 2026 calendar and Sat 3 Jul 2027 `1` on the 2027 calendar — the rollover week is still split. No league plays that week and no batch changed it |
| CORR-15 | 133, 159 | **partial** | The mechanism works — interleaved by date rank, stops cleanly on its budget, keeps what it bought (the batch's own tests pass against the scratch DB: `out/pytest-budget.txt`, 61 passed). But at **production's pool shape** the budget mis-prices a walk and the three-window acceptance fails: CORR-24 (`out/budget.txt`) |
| Batch 161 (installation bucket) | 161 | **held** | Charged exactly as `submit_pick` charges: three leagues × 40 submissions in one hour admitted 40 / 10 / 0 = **50**, the installation limit. The first league to spend can starve the others — documented and intended |
| Batch 115 (certification reads the DB) | 115 | **held, with a caveat** | `_database_round_shape` derives the largest round and its unpriced share from PostgreSQL and falls back to the dated 264 / 89 floor; run against the scratch DB it certified on the floor (largest round 6). The caveat is structural: the gate only ever runs against an empty scratch database, so in practice the floor is always what is certified, and `OBSERVED_DISTINCT_WINDOWS = 2` beside it is still a hand-typed constant nothing re-measures (INFO) |
| CORR-17 | 147 | **held** | The real `pick_reminders` trigger from `create_scheduler()` (`cron[minute='15']`, UTC) iterated across 24-26 Oct 2026 and 27-29 Mar 2027: 48 fires each, every gap exactly one hour. At each fire, `gameweeks_due_a_reminder` against rounds locking every 15 minutes from 20:00Z the evening before to 12:00Z on the change day (65 per night, including the repeated hour 00:00-02:00Z on 25 Oct): **every round reminded exactly once**, both nights (`out/dst.txt`) |
| CORR-05 (DST-hour window) | spot check | **held** | PATCH to a Sunday window at 01:00 or 01:30, or a 03:00 window with a 90-minute lock, → 422 naming the clock change |
| Batch 95 (off-site backup) | 95 | **held** | The real `run_offsite_backup()` against a **local fake S3** (an httpx transport storing files under the scratchpad, re-deriving the SigV4 signature and refusing a body whose SHA-256 differs; never R2): listing → dump (pgserver's `pg_dump`) → one signed PUT of a 72 KB archive. Restored with the runbook's own `pg_restore --clean --if-exists --no-owner --exit-on-error` into a fresh database: profiles, leagues, rounds, picks, the sum of points, every pick's status:points string, audit rows and `alembic_version 026` all identical. Misconfigured: missing secret and a non-https endpoint fail before any request; unreachable and a 403 listing fail after one GET and **before `pg_dump` runs**; a refused upload fails after the dump. Each writes `backup_failed` with a reason that never contains the secret; the first pushes the site admins, later ones that day are held by the 1/day cooldown. Not scheduled at all while `BACKUP_STORAGE=none`; Monday 04:00 London when on (`out/backup.txt`). A plain `pg_restore` without `--clean` fails on `CREATE SCHEMA public` — the runbook says so and uses `--clean` |
| CORR-10 | 131 | **held** | Settled L1 with two void legs (the fixture marked every runner `REMOVED`): Alice and Carol, void-only in L1, show `win_rate_pct = null` on `/standings` and Carol's `/players/{id}/profile`; Carol's cross-league summary reads 1 won of 2 played, 1 priced → **100%**, Alice's 1 won of 3 played, 2 priced → 50%; Bob (one loss) 0%. Every surface that shows a win rate reads `Standing.win_rate_pct` or divides by `picks_priced` (`out/lifecycle.txt`) |
| CORR-18 | 157 | **held** | `GET /me/cross-league-summary` carries neither `avg_rank` nor `avg_rank_leagues` for three members; the web source references them only in a comment (`lib/types.ts:654`) |
| void legs (owner decision) | 156 | **partial** | The coupon screen is right — `GET /coupon` for L1 returns `combined_odds 7.44` = 3.10 × 2.40 with `void_leg_count 2`, and the share text reads the same fields. But the Results list and home's "Last result" panel still multiply the void legs: **54.91** for the same round. CORR-21 |
| FEAT-A10 (pick correction) | 134 | **held**, gap in CORR-22 | `POST /admin/picks/{id}/correct` as the site admin flipped Bob lost → won 24; the repeat returned `changed: false` and wrote no audit row; a league admin got 403. Standings, the coupon (leg `won 24`, `all_won false`), the Results row (`picks_won` 1 → 2, winner still Dan on 31) and the cross-league summary all agreed on the next read. Two simultaneous corrections of Dan's pick with different scores serialised on the row lock: both 200, each reporting the true `before`, final state = the later one, two audit rows in order. No push was sent — CORR-22 |
| FEAT-B08 (settle notification) | 135 | **held**, gap in CORR-23 | `run_settle_gameweeks` with the clock pinned to Sat 3 Oct 20:00Z: one push per active, unmuted member of each settled round, each naming their own result ("won 31 points", "lost", "was void — no points", "You had no pick this round"); the muted L2 member got nothing; the member who had left L1 and the deleted member got nothing; a second sweep sent **zero** (`out/lifecycle-pushes.json`). The admin hand-entry path was not re-driven |
| FEAT-B07 (anonymise, keep history) | 136 | **held** | After Bob deleted his account: L1's live table shows "Former member 24", the 2025/26 archive "Former member 25" at #1, the Results row names "Former member" as that week's winner, his coupon leg reads "Former member won 2.40 24"; Alice's, Carol's and Dan's points, win rates and summaries were byte-identical before and after (`out/lifecycle.txt`) |

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| CORR-19 | MED | live | verified | A member deleting their own account completes the round silently, and the next pick change is announced as the completing pick |
| CORR-20 | MED | live | verified | A round the settle guard will never settle is still offered for picks, which then stay pending for ever |
| CORR-21 | LOW | live | verified | The Results list and home's "Last result" still multiply void legs into the combined price the coupon screen excludes |
| CORR-22 | LOW | live | verified | A pick correction is silent: the member told "lost" by the settle push is never told they won |
| CORR-23 | LOW | live | verified | A round nobody picked on never settles, so it is never announced and stays "locked" for ever |
| CORR-24 | MED | live | verified | Discovery's budget prices a walk at the raw pool (36) not what is walked (23): two walks a day at production's shape, and a third window is not served |
| CORR-25 | LOW | live (not yet run in production) | verified on scratch | The season-calendar backfill and the runtime re-anchor count a deleted league's rounds, so one early test round renumbers every live league |
| CORR-26 | LOW | live | verified | A settled coupon reads "4 of 3" once a member who picked has left or deleted their account |

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

## CORR-21 · LOW · live · verified — two surfaces still price the void legs

Batch 156 (owner decision: exclude void legs) changed `build_coupon` only. The same
round's combined price is also computed by `scoring.gameweek_results` (the Results list,
`scoring.py:773`) and by `me._last_results` / `me._latest_rounds` (home's "Last result"
panel and card, `me.py:469`, `me.py:552`), and all three still pass every leg's
`odds_at_pick` to `combined_odds`. L1's settled round with two void legs reads
`combined_odds 7.44` on the coupon and **54.91** on `/results` and in the
cross-league summary's `last_result` (`out/lifecycle.txt`). `leg_count` there also
includes the void legs, so home prints "4-fold · 54.91" beside a coupon that says
"2-fold @ 7.44 — 2 legs void, not in the price".

Confirmed in real Chromium on the production bundle (`notes/02-correctness/web_check.mjs`,
`out/web_check*.txt`): home's card reads "2 of 4 picks landed · 4-fold · 54.91", the
Results row "54.91", and tapping that row opens the coupon at "7.44 — 2 legs voided — not
in the combined price" (`screenshots/home--last-result-void--1280--light.png`,
`results--void-leg-price--…`, `coupon--settled-void-legs--…`).

**Member impact:** the same week's accumulator shows two different prices depending on
which screen a member opens.

**Fix:** filter void in the three other call sites (or have them share one helper with
`build_coupon`), and carry `void_leg_count` on `GameweekResult` and `LastResult`.
API-carrying; the web's two readers need the fold count adjusting.

## CORR-22 · LOW · live · verified — a correction never reaches the member

Batch 135 tells each member their result when a round settles; Batch 134's correction
rewrites that result afterwards and sends nothing (`routers/admin.py correct_pick`). In
the reproduction Bob received "Your pick, Celtic (v Rangers) @ 2.40, lost."; the site
admin then corrected him to won, 24 points; the captured push log stayed empty. Neither
row asks for a notification, so this is a gap rather than a regression — but the one
member whose result changed is the one person who will not look.

**Member impact:** a member told they lost is never told a correction gave them points.

**Fix:** after a correction that changes the result, send the same per-member settle
line (tagged `round-settled-…` so it replaces the old one in the tray), gated by the
league mute. API-carrying, small.

## CORR-23 · LOW · live · verified — a round with no picks never settles

`settle_gameweeks_via_provider` asks the provider only about rounds with pending picks
and returns early when there are none (`scoring.py`, unchanged since before 2ce6f42), so
a locked round nobody picked on is never flipped to `settled`. After the lifecycle run
the race league whose picks had been cleared (L4) and L5 were still `locked` a day after
their windows. Consequences since Batch 135: its members are never told "Gameweek N has
settled. You had no pick this round.", the round never reaches the Results list, and it
is re-selected by every settle sweep for ever. Rare in a live league (it needs every
member to miss the deadline), which is why LOW.

**Fix:** in `settle_gameweek(s)`, flip a locked round with no picks to `settled` once its
window has closed, then announce it like any other.

## CORR-24 · MED · live · verified — the discovery budget prices the wrong number

Batch 133 gave `run_discover_fixtures` a budget (`discovery_request_budget = 90`) and
charges each `(window, date)` walk `per_walk = len(set(competition_ids))`
(`services/gameweek.py`, in `discover_fixtures`). The job passes
`pooled_competition_ids()` — which its own docstring says is the **raw** pool, for the
caller to intersect — and `OddsApiProvider.fetch_slate` then walks only the pool ∩ the
played catalogue. The repo's own 2026-09-27 measurement (`services/competitions.py`) is
**36 pooled, 23 played**. So each walk is charged 36 and costs 23.

Driven in process (`notes/02-correctness/budget.py`, `out/budget.txt`) with
`discover_fixtures` called exactly as the two jobs call it and a stub that charges what
odds-api.io charges (one `/events` per played competition walked):

| distinct windows | daily run spends | walks | windows served | refresh (no budget) per run |
| --- | --- | --- | --- | --- |
| 1 | 46 | 2 of 2 | 1/1 | 23 |
| 2 (production, per `test_request_budget.py`) | 46 | 2 of 4 | 2/2 | 46 |
| 3 | 46 | 2 of 6 | **2/3** | 69 |
| 5 | 46 | 2 of 10 | 2/5 | **115** |

At two windows the run stops at half its budget and never pre-discovers the second week
of either window; at three, the acceptance line "the last window still served" fails —
the third window's next round is left to the 09:00 refresh. That refresh
(`run_refresh_slate`) has no budget at all, and at five windows spends 115 in one hour
against a 100/hour plan. With a raw-equals-played pool (the batch's own test data) the
arithmetic comes out right, which is why the gate is green.

**Disproof attempted.** Checked that `run_discover_fixtures` passes the raw pool
(`competition_ids=pooled or None`), that nothing trims it before `per_walk` is computed,
and that `odds_api.fetch_slate` does trim (`_uk_leagues` → `is_played`). The pool figures
are the repo's measurement, not production reads. The member-facing cost is modest because
the refresh catches each window's next round a few hours later, hence MED.

**Member impact:** rounds more than a week out are not created by the morning job, and in
a three-window deployment one league's next round appears hours later than the others'.

**Fix:** compute `per_walk` from the competitions that will actually be walked (intersect
with `is_played`, or pass `played(pooled)` from the job), and give `run_refresh_slate` the
same budget. API-carrying.

## CORR-25 · LOW · live · verified on scratch — a deleted league can move the anchor

`backfill_season_calendar.plan` derives each season's anchor from `min(canonical_saturday)`
over **every** round, joined to `leagues` with no `deleted_at` filter; the runtime
`reanchor_from_earliest_round` and `ensure_calendar_for_new_season` read `gameweeks` the
same way. Dry-run against a separate scratch database (`backfill_check`, dropped after;
`notes/02-correctness/backfill.py`, `out/backfill.txt`) seeded like the backfill note's
production description — a Saturday league 8 Aug-26 Sep numbered 1-8, a second league on
its own window (29 Aug = 1, 5 Sep = 3) — **plus one deleted league whose only round is
1 Aug**: the dry run anchors week 1 on **1 Aug**, and every live round moves one week
("Saturday League · 2026-08-08: was Gameweek 1 -> now Gameweek 2", …, 26 Sep "was 8 -> now
9"). The deleted league's own round is counted only in "unchanged round labels: 1", so the
dry run never names the row that caused the shift. `--apply` then stored 1 Aug and a
second dry run reported no moves, as the note says it must.

Whether production holds such a round is unknown (production is not read by this
review); the backfill note expects 8 Aug. The owner's review of the dry run is the
safeguard, but the line that would explain a surprising anchor is missing.

**Member impact:** if a deleted or test league ever played earlier in the season, applying
the backfill renumbers every live league's played weeks by one.

**Fix:** filter `League.deleted_at IS NULL` in `plan`, `reanchor_from_earliest_round` and
`ensure_calendar_for_new_season`'s count, and print the round that set each anchor in the
dry run. API-carrying; worth doing before the owner runs the backfill.

## CORR-26 · LOW · live · verified — "4 of 3"

`CouponSection.tsx` heads the coupon `${leg_count} of ${memberCount}`, where the member
count is the league's *current* active roster. Legs are kept for members who left (Batch
130 keeps their pick) and for erased members (Batch 136 keeps it by design), so after Erin
left L1 and Bob deleted his account, the settled Gameweek 1 coupon reads **"Result 4 of
3"** beside "3 of 3 picked" (`screenshots/coupon--settled-void-legs--1280--light.png`).
The share text's "incomplete" note is guarded against a negative count, so only the
header is wrong.

**Member impact:** a past coupon claims more picks than members, which reads as a bug.

**Fix:** head a settled coupon with the leg count alone ("4 picks"), or count members who
held a pick in that round rather than today's roster. Web-only.

## Checked and found nothing material

## Proposed batches

## Owner decisions

## Doc corrections

None found so far. (`docs/backfills/2026-season-calendar.md` is accurate for data with no
deleted-league rounds; CORR-25 is a code fix, not a doc correction.)

## What this pass did not do

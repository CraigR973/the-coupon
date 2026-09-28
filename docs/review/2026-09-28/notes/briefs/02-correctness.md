# Lens 02 — Correctness

Output: `docs/review/2026-09-28/02-correctness.md`. Notes: `docs/review/2026-09-28/notes/02-correctness/`.
Ports: API **8120**, web **4320**. New finding ids start at **CORR-19**.

Judge against the product contract at the top of `docs/BUILD_PLAN.md` and each
batch row's acceptance text, not intuition. Any single-league or single-window
assumption is a bug.

## Your slice of the 2026-09-13 register (re-drive each against a running stack)

| id | sev then | batch | what "fixed" should look like |
| --- | --- | --- | --- |
| CORR-08 | HIGH | 120 | ≥10 concurrent submissions for one selection, in **both** claim scopes: exactly one 201, zero 500s, the rest the documented conflict code, CORS header present on the 409s |
| CORR-09 | HIGH | 121 | a Saturday→Friday window change mid-week leaves exactly one scoring round per football week; a stray already holding a pick is reported, not silently scored; Batch 112 retirement still holds |
| CORR-13 | MED | 121 | no two rounds in one football week share a bare label |
| CORR-14 | MED | 130 | last outstanding picker leaving / removed / deactivated completes the round once, correctly attributed; a later pick change does not re-complete |
| CORR-10 | MED | 131 | void excluded from the win-rate denominator (check every surface that shows a win rate, not just one) |
| CORR-11 | MED | 132 | declaring an extra week in a past or settled week is refused |
| CORR-12 | MED | 132 | anchor = earliest canonical Saturday across all leagues' first rounds, regardless of discovery order |
| CORR-15 | MED | 133 | a three-window shape completes discovery inside its budget with the last window still served; exhaustion leaves every completed (window, date) committed |
| CORR-16 | LOW | accepted, no action | confirm still true and still harmless |
| CORR-17 | LOW | 147 | a round locking in the repeated hour on **2026-10-25** is reminded exactly once — this is four weeks away, so be precise |
| CORR-18 | LOW | 157 | `avg_rank` / `avg_rank_leagues` gone from the summary and the web |
| void legs | owner decision | 156 | the combined coupon multiplies only non-void legs; the screen and the clipboard share text agree and say a leg was voided |

## What to do

1. Stand up the harness, then seed **at least two leagues** in process with
   deliberately different configurations — e.g. League 1 on defaults (Saturday
   15:00, lock 30 min before, `MATCH_ODDS`, `selection` scope) and League 2 on a
   Friday evening window with a 60-minute lock, both markets, a competition
   subset and `fixture` scope — with members in both, some on non-London profile
   timezones. Keep the seeding script in your notes.
2. Play both through **open → pick → claim conflict → lock → settle → standings
   → combined coupon → season archive**, over HTTP, advancing lock and settle
   with the scheduler's own job functions against the scratch database (the
   prior review did exactly this). Use the web bundle for the member-facing half
   where it matters (the conflict and void-leg messaging).
3. Priorities, beyond the table: **pick correction (134)** — correct a settled
   pick and prove standings, the combined coupon, career stats and the
   settlement notification all agree afterwards; idempotent; audited. **Account
   deletion (136)** — after a member is anonymised, do settled points still sum
   into every historic standing and the season archive, and does the coupon
   still show their leg? Do win rates and career numbers of *other* members
   change? **The settlement notification (135)** — both settle paths, once only,
   muted leagues silent, correct per-member result; what does a pick correction
   do to it? **Discovery and slate budgets (115, 133, 159, 161)** — drive with a
   counting fake provider and a three-window shape; check the Batch 115
   certification reads the database. **Backup job (95)** — run it against a
   **local fake target** (a directory or a local S3-compatible stub — never R2,
   never production), prove a dump is written and restorable into a fresh
   scratch database, and that it refuses or fails loudly when misconfigured.
4. **Season-calendar backfill dry-run** (`python -m src.backfill_season_calendar
   --dry-run`, see `docs/backfills/2026-season-calendar.md`) against **your
   scratch database only**, with a realistic seeded season. Never `--apply`
   anywhere but scratch, and never with production credentials.
5. **Time**: DST weekends (the 2026-10-25 fall-back and 2027-03-28
   spring-forward), London vs UTC boundaries (a round on the day the clocks
   change, a member in New York), lock instants and pick-open instants.
6. **Concurrency**: concurrent claims on one selection (both scopes);
   concurrent last-two-slots completion; a pick racing a lock; a pick racing a
   member's own deletion; two admins correcting the same pick.
7. A sweep of everything changed since `2ce6f42` under `apps/api/src` for naive
   local-time arithmetic, hardcoded Saturday/15:00, unfiltered "latest round"
   lookups, and queries missing a `league_id` or `deleted_at` filter.

## Notes

The prior review's method paragraph (02-correctness.md there) is the model.
Record the exact reproduction for anything you report.

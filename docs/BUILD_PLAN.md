# The Coupon — build plan

## Product contract

The Coupon is a private weekly football accumulator game for friends.

- One global gameweek contains that Saturday's 15:00 fixtures.
- Each leaderboard member makes one `MATCH_ODDS` or
  `BOTH_TEAMS_TO_SCORE` pick.
- A selection can be held by only one member of a leaderboard.
- Odds are read from Betfair and frozen when the pick is submitted.
- Picks lock at 14:30 Europe/London.
- A winning pick scores `round(odds × 10)`; a losing pick scores zero.
- Standings are the season sum of settled pick points.
- The combined coupon multiplies every member's frozen odds.
- The product is for points and fun and never places a wager.

## Architecture

The FastAPI backend owns auth, leagues, the weekly slate, pick uniqueness,
settlement, standings, notifications, and scheduled jobs. PostgreSQL is the
source of truth. The React PWA consumes snake_case `/api/v1/` JSON.

`BetfairAdapter` contains the domain mapping for slate, prices, and market
results. `Betfair` implements the live HTTP client. `FakeBetfair` supplies the
same catalogue and market-book shapes for deterministic tests.

## Build batches

This checklist is the batch source of record. Close-out ticks a batch only
after the user invokes `/phase-closeout <N>`.

- [x] **Batch 1 — Application spine** ✅ 2026-07-25 — PIN auth, profiles,
  notifications, leagues, memberships, join requests, invites, scheduler
  framework, and baseline migration.
- [x] **Batch 2 — Betfair adapter** ✅ 2026-07-25 — live client, shared domain
  mapping, canned implementation, retries, prices, and settlement.
- [x] **Batch 3 — Pick and scoring engine** ✅ 2026-07-26 — gameweeks, fixtures,
  picks, both uniqueness constraints, odds scoring, standings, and combined
  coupon.
- [x] **Batch 4 — Scheduler** ✅ 2026-07-26 — slate refresh, reminders, locking,
  settlement, and shared live-session lifecycle.
- [x] **Batch 5 — Frontend reshape** ✅ 2026-07-26 — weekly pick UI, combined
  coupon, home, standings, and current API binding.
- [x] **Batch 6 — Verify + rebrand pass** ✅ 2026-07-26 — run every verification gate below,
  remove inherited product naming and unused surfaces, replace inherited
  documentation and assets, and delete the temporary handoff document.

## Verification

- **Backend:** pytest covers both pick-uniqueness directions, odds scoring,
  combined-odds multiplication, the canned Betfair adapter, locking, and
  settlement. Ruff check/format and strict mypy pass.
- **Database:** `alembic upgrade head` succeeds on clean `pgserver` PostgreSQL;
  the baseline tables exist and no legacy tables exist.
- **Frontend:** Node 20 production build, `tsc --noEmit`, and Vitest pass.
- **Browser end-to-end:** against a production preview, real scratch PostgreSQL,
  and `FakeBetfair`, seed a leaderboard and members; show the Saturday slate;
  submit two members' picks; show a third member blocked from a taken
  selection; lock; settle canned results; verify updated standings and the
  combined coupon; save screenshots.
- **Live Betfair:** the owner alone uses their session to confirm a real Saturday
  slate and prices. This is not an agent action.

## Launch gates

Fresh Supabase, Railway, Vercel, domain naming, real league membership, and any
non-interactive Betfair certificate are separate launch work. The audited,
ordered launch checklist is in `docs/LAUNCH_PLAN.md`.

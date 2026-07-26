# The Coupon — session log

## Batch 1 — Application spine
**Commits:** `8513a02` · verified: Ruff · mypy · 76 pytest · migration + league flow

### Key facts for future sessions
- No local backend venv; use the sibling template venv with this repo's `PYTHONPATH`.
- Scratch database checks use pip `pgserver`.
- The baseline migration contains profiles, tokens, notifications, leagues,
  memberships, join requests, and invites.

**Next:** Batch 2 — Betfair adapter

## Batch 2 — Betfair adapter
**Commits:** `21078d6` · verified: Ruff · mypy · 98 pytest

### Key facts for future sessions
- Domain mapping lives on `BetfairAdapter`; live and canned implementations
  override only raw API primitives.
- `FakeBetfair.with_sample_data()` includes an English top-flight match, a
  Scottish fourth-tier match, a non-15:00 decoy, and one unpriced selection.
- Never use the owner's live account in agent verification.

**Next:** Batch 3 — Pick and scoring engine

## Batch 3 — Pick and scoring engine
**Commits:** `433f0ae` · verified: Ruff · mypy · 116 pytest · scratch migration + pick flow

### Key facts for future sessions
- Gameweeks and fixtures are global; picks are league-scoped.
- The submit endpoint reads odds server-side and snapshots the chosen price.
- HTTP pick-flow tests commit; reset the scratch schema before rerunning them.
- `alembic check` has known model/default drift; `upgrade head` is the gate.

**Next:** Batch 4 — Scheduler

## Batch 4 — Scheduler
**Commits:** `bc40245` · verified: Ruff · mypy · 149 pytest on scratch PostgreSQL

### Key facts for future sessions
- Jobs use Europe/London wall time and own their database transaction.
- The live adapter uses one shared login with keep-alive and transparent
  reauthentication; tests override the dependency with `FakeBetfair`.
- Lock and settlement jobs are also callable from the external cron entrypoint.

**Next:** Batch 5 — Frontend reshape

## Batch 5 — Frontend reshape
**Commits:** `25133f0` · verified: build · TypeScript · 169 Vitest

### Key facts for future sessions
- Pick, combined-coupon, and standings screens use the snake_case API directly.
- Query keys are centralised in `usePickEditor`; standings use
  `['standings', slug]`.
- The top-level coupon is a single-leaderboard MVP; per-league coupon routing is
  later product work.

**Next:** Batch 6 — Verify + rebrand pass

## Batch 6 — Verify + rebrand pass
**Commits:** `72945c0` · verified: 149 pytest + Ruff/mypy · scratch migration · build/TypeScript + 168 Vitest · mocked browser E2E · grep clean

### Key facts for future sessions
- Browser verification uses `tests.e2e_server:app`, disposable PostgreSQL, and
  `FakeBetfair`; production never imports the test control endpoints.
- The MVP default league slug is `the-coupon`; browser storage and cache keys
  use the `coupon_*` namespace.
- Display-name + PIN auth and invite claiming now use only the live snake_case
  API surface.
- Inherited product documentation, assets, routes, scripts, and the temporary
  handoff document were removed.
- The owner's live Betfair account remains outside agent automation.

**Next:** Launch planning (all build batches closed)

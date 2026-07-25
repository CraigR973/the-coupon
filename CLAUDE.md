# World Cup 2026 Prediction League — CLAUDE.md

This file provides Claude with project-specific context and configuration for every session.

---

## Project

**World Cup 2026 Prediction League** — a private, invite-only prediction league PWA for the 2026 FIFA World Cup. Up to 15 players, full tournament coverage (104 matches), automatic result fetching, live leaderboard, push notifications.

**Stack:** FastAPI + PostgreSQL (Supabase) + React 18 + Tailwind + shadcn/ui  
**Auth:** Name + PIN (bcrypt) with JWT access (24h) + refresh (30d) token pair  
**Hosting:** Vercel (frontend) + Railway (backend)

---

## Phase close-out protocol

Close-out is triggered by `/phase-closeout <N>` (N = batch number; canonical steps in
`docs/agent-commands/phase-closeout.md`). Do not auto-run it at end-of-batch — wait for the
slash command so the user can review the work first. The global `~/.claude/CLAUDE.md` defers
to this same explicit-trigger rule.

- **Batch source of record:** `docs/BUILD_PLAN.md` — a checklist of `- [ ] **Batch N —`
  rows. Close-out ticks the row; `/next-batch-prompt` reads the first un-ticked one.
  There is **no** `phase-batches.md` / `wc2026-architecture.md` here — those were calcio's.
- Session log: `session-log.md` (repo root)
- **Local-only right now:** no git remote, no CI, no staging/prod (its own GitHub remote +
  Supabase/Railway/Vercel are gated to launch — see BUILD_PLAN "Out of scope"). So the green
  gate is **local** (`ruff` · `ruff format` · `mypy` · `pytest`, plus a `pgserver` migration
  check when models/migrations changed), and close-out ff-merges the `feat/` branch to **local**
  `main`. The `docs/agent-commands/phase-closeout.md` 🚩 REMOTE-TODO markers show where
  push / CI-poll / deploy slot in once that infra exists.

### MANDATORY: generating the next-batch prompt

Follow `docs/agent-commands/next-batch-prompt.md`: `grep` `docs/BUILD_PLAN.md` for the first
`- [ ]` batch row, use its description verbatim as the scope (plus the relevant BUILD_PLAN
"Verification" bullets as acceptance), and carry gotchas from the last `session-log.md` entry.
NEVER invent a batch or acceptance criteria. Model tag (🟢 Sonnet default / 🔴 Opus for
scoring, scheduler, Betfair sync) is a suggestion, not fixed.

### Session log entry format (use this, override the global protocol's verbose template)

```
## Batch N — Title
**Commits:** <hash>[, <hash>] · verified: ruff · mypy · pytest[ · migration/e2e]

### Key facts for future sessions
- <only non-obvious gotchas a future session can't discover by reading code or `git log`>
- <max ~6 bullets>

**Next:** Batch N+1 — Title
```

That is the whole entry — commits, verify marker, key facts, next pointer. Date, model,
files-modified, what-shipped are ALL recoverable from `git show <hash>` / `git log` and must
NOT be duplicated. Keep entries under ~15 lines.

---

## Bash discipline (token-saving)

- **Never `cd`.** The sandbox blocks `cd` outside the worktree root and each blocked call wastes a turn. Use absolute paths in every command.
- Python interpreter for backend work: `/Users/craigrobinson/wc_2026_predictor/apps/api/.venv/bin/python` — the venv is NOT inside the worktree.
- Backend test/lint/typecheck invocation pattern:
  - `PYTHONPATH=<worktree>/apps/api /Users/craigrobinson/wc_2026_predictor/apps/api/.venv/bin/python -m pytest <abs-path-to-tests>`
  - Same shape for `-m ruff check`, `-m ruff format --check`, `-m mypy src`
- Frontend test invocation: `PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH" pnpm --dir <worktree>/apps/web test`
- Prefer `grep` with line ranges over reading whole files. `wc2026-architecture.md` is 1600+ lines — always grep for the section heading first, then read a small `offset`/`limit` window.
- **Spawn the Explore subagent when investigating >3 files** to answer a "where is X / how is Y wired" question. Explore returns a summary at much lower token cost to the main session than 5–8 grep + read calls in main context.

---

## Key files

| File | Purpose |
|---|---|
| `wc2026-architecture.md` | Authoritative design spec — all phases, data model, API design |
| `session-log.md` | Running log of completed phases and session notes |
| `apps/api/` | FastAPI backend |
| `apps/web/` | React frontend (Vite) |
| `packages/shared/` | Shared Zod schemas, TS types, scoring logic |
| `migrations/` | Alembic migrations |
| `docs/runbooks/` | Operational runbooks (restore, kickoff change, cancelled match, PIN reset, etc.) |
| `docs/phase-batches.md` | Multi-phase session batches for amortizing the cold system prompt — consult at close-out |
| `.env.example` | All required environment variables documented |

---

## Environment variables

All required variables are documented in `.env.example` with inline comments. Read that file when you need a specific name or purpose; do not duplicate them here.

---

## Conventions

- All endpoints prefixed `/api/v1/`
- Standard response envelope: `{ data, meta, errors }`
- Database: snake_case, UUID PKs, soft deletes on critical tables
- API JSON: camelCase
- Git branches: `feat/`, `fix/`, `chore/` prefixed, squash merge to `main`
- Commits: Conventional Commits format
- Tests ship with every phase — no phase is done without them
- Never skip acceptance criteria — a phase isn't complete until every bullet passes

---

## Time and timezone handling

- All timestamps stored in **UTC** in the database (`TIMESTAMP` columns named `*_utc`)
- Each player has a `profiles.timezone` field storing their **IANA timezone** (e.g. `Europe/London`, `America/New_York`)
- The frontend converts UTC to player-local time using `date-fns-tz`
- The 2026 World Cup matches span US/Canada/Mexico time zones — players in the UK will see kickoff times in their own timezone correctly
- APScheduler jobs use UTC throughout; never assume server timezone
- When displaying a kickoff: always pass through `formatInTimeZone(kickoffUtc, player.timezone, 'EEE d MMM, HH:mm')`

---

## Scoring rules

The authoritative scoring rules live in `wc2026-architecture.md` (§7) and the Postgres trigger in `migrations/`. Read them on-demand when touching scoring logic.

---

## Phase model guide

| Tag | When to use |
|---|---|
| 🟢 Sonnet 4.6 | Default — CRUD, components, migrations, tests, API wiring |
| 🔴 Opus | Complex reasoning — scoring edge cases, bracket logic, scheduler, realtime sync, debugging |

---

## Current status

See `session-log.md` for the latest completed phase and next steps.

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

Close-out is triggered by `/phase-closeout <ids>` (see `.claude/commands/phase-closeout.md`). Do not auto-run it at end-of-phase — wait for the slash command so the user can review the work first. The global `~/.claude/CLAUDE.md` defers to this same explicit-trigger rule.

- Session log: `session-log.md` (repo root)
- Architecture/plan doc: `wc2026-architecture.md` (repo root)
- Remote: `origin main`
- After CI is green, merge the feature branch back to `main` via `git checkout main && git merge --ff-only <branch> && git push origin main`
- CI: GitHub Actions — token in `.env` as `GITHUB_TOKEN`. **Do not foreground-poll CI in a tight loop** — each iteration pollutes chat context. Pattern: one immediate check, then one or two follow-up checks via `run_in_background` bash spaced ~3 min apart, OR push and rely on the cached result endpoint at the end. Never write 10+ polling lines into the conversation.

### MANDATORY: generating the next-phase prompt

When writing the next-phase copy-paste prompt at close-out, you MUST:

1. `grep` `docs/phase-batches.md` to find the next un-struck-through batch. The prompt scope is **the entire batch**, not a single phase. A batch may contain 1–4 phases.
2. For every phase ID in the batch, `grep -n -A 6 "Phase X.Y:" wc2026-architecture.md` to pull the acceptance criteria verbatim. NEVER invent a phase number. If `grep` returns no match, the phase does not exist — stop and ask the user.
3. The model tag (🟢 Sonnet / 🔴 Opus) is fixed by the batch row. Do not propose a different model.
4. After the user starts the next session, strike through or delete the completed batch row in `docs/phase-batches.md` as part of close-out.

If `docs/phase-batches.md` does not exist or has no remaining batches, fall back to grepping `wc2026-architecture.md` for the next unticked phase heading — but say so explicitly so the user can confirm.

### Session log entry format (use this, override the global protocol's verbose template)

```
## Phase X.Y — Title
**Commits:** <hash>[, <hash>] · CI ✅

### Key facts for future sessions
- <only non-obvious gotchas a future session can't discover by reading code or `git log`>
- <max ~6 bullets>

**Next:** Phase X.Z — Title (model tag)
```

That is the whole entry — commits, CI marker, key facts, next pointer. Date, model, files-modified, what-shipped are ALL recoverable from `git show <hash>` / `git log --format=%ci %an` and must NOT be duplicated. Keep entries under ~15 lines.

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

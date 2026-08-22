# The Coupon — agent instructions

## Product

The Coupon is a private weekly football accumulator game. **A member may play in
several leagues at once, and each league is its own game** — it owns its rounds,
its weekly fixture window, which markets it offers, which competitions it draws
from, and how much of a fixture one claim takes. Each member claims one selection
per league per round, unique within that league; odds are frozen at pick time and
a winner scores `round(odds × 10)`.

The defaults reproduce the original single-league rule — one Saturday 15:00
slate locking at 14:30 Europe/London — so that is what an unconfigured league
plays, but nothing in the schema or the API assumes it. Treat any single-league
or single-window assumption in code you touch as a bug.

Stack: FastAPI + PostgreSQL, React 18 + TypeScript + Vite, and a provider-neutral
odds port (`odds-api.io` priced by Bet365 in production; a Betfair Exchange
fallback; canned data for tests). Authentication is display name + four-digit PIN.

## Source of record

- Product, batch checklist, and acceptance: `docs/BUILD_PLAN.md`
- Launch checklist and acceptance: `docs/LAUNCH_PLAN.md`
- Current implementation state: `STATUS.md`
- Completed-batch notes: `session-log.md`
- Completed-launch notes: `launch-log.md`
- Canonical slash-command workflows: `docs/agent-commands/`

When the user invokes a slash command, read and follow its matching canonical
file:

- `/next-batch-prompt <mode>` → `docs/agent-commands/next-batch-prompt.md`
- `/batch-start <id>` → `docs/agent-commands/batch-start.md`
- `/batch-verify <id>` → `docs/agent-commands/batch-verify.md`
- `/phase-closeout <id>` → `docs/agent-commands/phase-closeout.md`
- `/strike-batch <id>` → `docs/agent-commands/strike-batch.md`
- `/launch-start <L0-L5>` → `docs/agent-commands/launch-start.md`
- `/launch-verify <L0-L5>` → `docs/agent-commands/launch-verify.md`
- `/launch-closeout <L0-L5>` → `docs/agent-commands/launch-closeout.md`
- `/ship-staging [message]` → `docs/agent-commands/ship-staging.md`
- `/ship-prod` → `docs/agent-commands/ship-prod.md`

Close-out is explicit. Do not commit, merge, tick a build batch, or append its
final session-log entry until the user invokes `/phase-closeout <id>`. Do not
commit, merge, tick a launch phase, or append its final launch-log entry until
the user invokes `/launch-closeout <L0-L5>`.

## Toolchain

Never `cd`; use absolute paths or a tool working directory.

### The gate is one command

```bash
scripts/ci-local.sh              # everything CI runs; SKIP_PROD_BUNDLE=1 to drop the slowest job
```

**Use this before close-out, not the piecemeal commands below.** It builds its own venv
from `apps/api/requirements-dev.txt`, so the versions match the pins rather than whatever
is on `PATH`; it starts a clean `pgserver` and runs `alembic upgrade head` before pytest,
so the **151 Postgres-backed tests actually execute** instead of skipping; and it checks
the deployment config and the frontend as well. Ten checks, no skips.

Running pytest without `DATABASE_URL` is **509 passed, 151 skipped**, and the skipped set
is the HTTP pick flow, settlement, the scheduler jobs, slate persistence, seeds and every
migration test — that is, the core of the game. A green run in that mode says very little.

### Running one thing at a time

The commands below are for iterating on a single file. They are not the gate.

Backend:

```text
PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api
/Users/craigrobinson/app-starter/apps/api/.venv/bin/{python,mypy}
```

**That borrowed venv cannot collect the suite.** It has no Pillow, which Batch 44 made a
dependency of `services/avatar_storage.py`, so ten test modules — `test_auth`,
`test_picks_flow`, `test_health` among them — fail at import with
`ModuleNotFoundError: No module named 'PIL'`. It is fine for a quick `mypy` and nothing
else. `scripts/ci-local.sh` builds a complete one; reuse it directly if you want a shell:

```text
/Users/craigrobinson/.cache/the-coupon/ci-local-venv/bin/{python,ruff,mypy,alembic}
```

**Ruff is the exception — run the pinned version, not the venv's.** The borrowed
venv ships a far newer ruff than `apps/api/requirements-dev.txt` pins, and they
format differently, so the venv's copy can pass locally and still fail CI:

```text
RUFF="ruff==$(sed -n 's/^ruff==//p' /Users/craigrobinson/the-coupon/apps/api/requirements-dev.txt)"
uvx "$RUFF" check /Users/craigrobinson/the-coupon/apps/api
uvx "$RUFF" format --check /Users/craigrobinson/the-coupon/apps/api
```

`mypy` also diverges from its pin (venv 2.x versus a 1.11 pin) but currently
agrees; see `docs/agent-commands/batch-verify.md` for why that one is left alone.

Frontend:

```text
PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
pnpm --dir /Users/craigrobinson/the-coupon/apps/web <command>
```

Use the pip `pgserver` package for scratch PostgreSQL. Start DB-backed reruns
from a clean schema because the HTTP pick-flow test commits.

## Conventions

- Work on `feat/`, `fix/`, or `chore/` branches; never implement on `main`.
- Endpoints use `/api/v1/` and snake_case JSON.
- PostgreSQL uses snake_case and UUID primary keys.
- Store timestamps in UTC; schedule weekly locks in `Europe/London`.
- Tests ship with every batch.
- Never log into the owner's live Betfair account. Automated verification uses
  `ODDS_PROVIDER=fake`; the owner performs the live slate and pricing checks.
- `fetch_odds` runs in the request path and `odds-api.io` allows 100 requests/hour
  and 500/day, so the provider handed to a request must be the cached one.
- When investigating more than three files to learn where behavior is wired,
  use an Explore subagent.

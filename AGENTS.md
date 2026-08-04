# The Coupon — agent instructions

## Product

The Coupon is a private weekly football accumulator game. A global gameweek
contains one Saturday 3pm slate. Each leaderboard member claims one unique
`MATCH_ODDS` or `BOTH_TEAMS_TO_SCORE` selection; odds are frozen at pick time,
picks lock at 14:30 Europe/London, and a winner scores `round(odds × 10)`.

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

Backend:

```text
PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api
/Users/craigrobinson/app-starter/apps/api/.venv/bin/{python,ruff,mypy}
```

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

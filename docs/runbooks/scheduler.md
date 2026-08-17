# Scheduler Runbook

The MVP scheduler runs inside the single always-on Railway API process.

## Normal Operation

- Keep exactly one API replica.
- Keep sleep/serverless behavior disabled.
- Keep `SCHEDULER_ENABLED=true` on the scheduler-owning service.
- Check Railway logs for `fixtures discovered`, `slate refreshed`, `gameweeks
  locked`, `gameweeks settled`, and `pick reminders sent`.

## One-Off Commands

Run from the backend service environment:

```bash
python -m src.run_scheduled discover-fixtures
python -m src.run_scheduled refresh-slate
python -m src.run_scheduled remind
python -m src.run_scheduled lock
python -m src.run_scheduled settle
python -m src.run_scheduled sync-football
python -m src.run_scheduled football-backfill
```

The command exits non-zero when the job logs an internal failure.

The two football jobs spend a **100-request day**, so they are the two to think
before running: a full `sync-football` sweep costs one catalogue request plus two
per competition (about 61 for a 30-competition card) and takes roughly six minutes
at the 12-second spacing the minute ceiling requires. `football-backfill` is
unbounded in date and is a one-off for a new deployment or a season change, not a
thing to re-run. Confirm the day's allowance is intact before either — a failed run
still spends what it sent.

## Fixture discovery vs slate refresh

Batch 11 split the two. `discover-fixtures` runs daily at 06:00 Europe/London and
walks the next `SLATE_HORIZON_WEEKS` Saturdays (default 2) into `fixtures`, so a
member picking on Tuesday already has a full card. `refresh-slate` is the late
match-day pass — Saturdays at 09:00 and 13:00 — that catches postponements and
kick-off changes.

Neither job fetches odds. Prices are requested on demand and served from a cache
whose ceiling tightens as lock approaches; the price a member is actually scored
on is refreshed at submit time for that one fixture. `tests/test_request_budget.py`
holds the whole arrangement to the provider's 100/hour and 500/day.

## Settlement Retries

Settlement runs Saturday, Sunday, and Monday at 18:00, 20:00, and 22:00
Europe/London. Settlement is derived from the provider's published score, so a
fixture whose score lands late simply stays pending; re-run `settle` manually if a
result appears after the final retry.

## Staging lifecycle rehearsal

`scripts/agent/l3-staging-control.py` drives the deterministic L3 story using
the real scheduler functions and canned `FakeBetfair` markets. It refuses any
environment except staging and requires `ODDS_PROVIDER=fake`. Its output contains
counts and state only.

Use the exact staging Railway selectors with `railway run --no-local`, and keep
the synthetic PIN in a mode-`0600` local file or process environment. Never
place a PIN on the command line or in a log. The expected sequence is:

1. `reset-credentials`
2. complete the open-gameweek browser flow
3. `force-lock`
4. verify the locked browser flow
5. `settle-open` to prove an open market leaves picks pending
6. `settle-closed` to prove the retry resolves the canned winners
7. verify standings and the combined coupon

The control is for designated synthetic staging data only. It is not copied
into the production image and must never be used with a live odds provider.

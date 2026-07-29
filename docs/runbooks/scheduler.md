# Scheduler Runbook

The MVP scheduler runs inside the single always-on Railway API process.

## Normal Operation

- Keep exactly one API replica.
- Keep sleep/serverless behavior disabled.
- Keep `SCHEDULER_ENABLED=true` on the scheduler-owning service.
- Check Railway logs for `slate refreshed`, `gameweeks locked`, `gameweeks
  settled`, and `pick reminders sent`.

## One-Off Commands

Run from the backend service environment:

```bash
python -m src.run_scheduled refresh-slate
python -m src.run_scheduled remind
python -m src.run_scheduled lock
python -m src.run_scheduled settle
```

The command exits non-zero when the job logs an internal failure.

## Settlement Retries

Settlement runs Saturday, Sunday, and Monday at 18:00, 20:00, and 22:00
Europe/London. Re-run `settle` manually if Betfair marks a market closed after
the final retry.

## Staging lifecycle rehearsal

`scripts/agent/l3-staging-control.py` drives the deterministic L3 story using
the real scheduler functions and canned `FakeBetfair` markets. It refuses any
environment except staging and refuses live Betfair mode. Its output contains
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
into the production image and must never be used with a live Betfair account.

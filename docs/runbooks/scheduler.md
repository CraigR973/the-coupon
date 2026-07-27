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

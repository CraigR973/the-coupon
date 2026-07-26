# Agent commands

These files are the canonical workflows for The Coupon. Tool-specific command
wrappers point here.

Normal flow:

```text
/next-batch-prompt
/batch-start <N>
<implement and test>
/batch-verify <N>
/phase-closeout <N>
```

Implementation belongs on a feature branch. Close-out is always an explicit
user action and is the only workflow that commits, merges to local `main`,
ticks `docs/BUILD_PLAN.md`, and appends a final session-log entry.

The repository has no remote or deployment environments yet. The two ship
commands therefore stop safely until launch infrastructure is configured.

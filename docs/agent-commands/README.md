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

Launch flow:

```text
/launch-start <L0-L5>
<implement only that launch phase>
/launch-verify <L0-L5>
/launch-closeout <L0-L5>
```

Implementation belongs on the working branch created by the matching start
workflow. Close-out is always an explicit user action and is the only workflow
that commits, integrates, ticks the applicable source-of-record checklist, and
appends a final log entry. Build history is recorded in `session-log.md`;
launch history is recorded in `launch-log.md`.

The repository has no remote or deployment environments yet. The two ship
commands therefore stop safely until launch infrastructure is configured.

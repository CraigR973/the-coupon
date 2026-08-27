# Agent commands

These files are the canonical workflows for The Coupon. Tool-specific command
wrappers point here.

Normal flow:

```text
/next-batch-prompt
/batch-start <N>   # branches, implements, and verifies the batch
/phase-closeout <N>
```

`/batch-verify <N>` still exists standalone for re-running the checks (e.g.
after manual follow-up edits) without redoing the implementation step.

Launch flow:

```text
/launch-start <L0-L5>
<implement only that launch phase>
/launch-verify <L0-L5>
/launch-closeout <L0-L5>
```

Implementation belongs on the working branch created by the matching start
workflow — for batches, `/batch-start` does this itself. Close-out is the only
workflow that commits, integrates, ticks the applicable source-of-record
checklist, and appends a final log entry. **Build-batch close-out runs
automatically** after a green `/batch-start` gate (owner decision, 2026-08-27;
see `AGENTS.md`), and its push deploys the web app. **Launch close-out remains an
explicit user action.** Build history is recorded in `session-log.md`; launch
history is recorded in `launch-log.md`.

The repository has no remote or deployment environments yet. The two ship
commands therefore stop safely until launch infrastructure is configured.

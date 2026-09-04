# Agent commands

These files are the canonical workflows for The Coupon. Tool-specific command
wrappers point here.

Normal flow:

```text
/next-batch-prompt
/batch-start <N>       # one batch: branch, implement, verify, close out
    or
/group-start <I-M>     # one group: separate batches until a ship checkpoint
```

`/batch-verify <N>` still exists standalone for re-running the checks (e.g.
after manual follow-up edits) without redoing the implementation step.
`/phase-closeout <N>` also remains directly invokable, although a green
`/batch-start` runs it automatically.

`/group-start` is resumable. It closes each batch through the normal workflow,
then stops before any required production API deployment. Invoke `/ship-prod`
separately and rerun the same group command; it verifies deployment drift is in
sync before continuing. A group command never combines batches on one branch or
deploys Railway.

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

The exact staging and production targets, their preflight checks, and their
fail-closed safeguards live in the two ship command files. Never infer a target
from an ambient CLI project link.

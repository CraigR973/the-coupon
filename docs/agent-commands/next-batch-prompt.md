---
description: Generate the next Coupon batch prompt from the checked build plan.
---

# /next-batch-prompt

1. Read `STATUS.md` (one page of current state), the head of `docs/BUILD_PLAN.md`
   down to its `## Closed batches` heading — the product contract, the
   architecture and every open row — and the latest `session-log.md` section,
   which is the last one in the file:

   ```bash
   sed -n '1,/^## Closed batches/p' /Users/craigrobinson/the-coupon/docs/BUILD_PLAN.md
   ```

   Do not read the closed rows below that heading, or the archive at the top of
   `session-log.md`, unless the row you are about to emit names one of them.
2. Locate the first unchecked row:

   ```bash
   grep -nE "^- \[ \] \*\*Batch [0-9]" /Users/craigrobinson/the-coupon/docs/BUILD_PLAN.md
   ```

3. If none remains, report that all planned batches are closed.
4. Otherwise emit a self-contained prompt containing:
   - the exact unchecked batch row as scope;
   - the relevant Verification bullets verbatim;
   - still-relevant gotchas from the preceding session-log entry;
   - the backend and frontend toolchain from `AGENTS.md`;
   - instructions to work on a `feat/` branch, ship tests, and close out
     automatically on a green gate per `AGENTS.md` — noting that the close-out
     push deploys the web half to members.

Never invent a batch or acceptance criterion. The user chooses the model.

---
description: Generate the next Coupon batch prompt from the checked build plan.
---

# /next-batch-prompt

1. Read `STATUS.md`, `docs/BUILD_PLAN.md`, and the latest `session-log.md`
   section.
2. Locate the first unchecked row:

   ```bash
   grep -nE "^- \[[ x]\] \*\*Batch [0-9]" /Users/craigrobinson/the-coupon/docs/BUILD_PLAN.md
   ```

3. If none remains, report that all planned batches are closed.
4. Otherwise emit a self-contained prompt containing:
   - the exact unchecked batch row as scope;
   - the relevant Verification bullets verbatim;
   - still-relevant gotchas from the preceding session-log entry;
   - the backend and frontend toolchain from `AGENTS.md`;
   - instructions to work on a `feat/` branch, ship tests, and stop before
     `/phase-closeout <N>`.

Never invent a batch or acceptance criterion. The user chooses the model.

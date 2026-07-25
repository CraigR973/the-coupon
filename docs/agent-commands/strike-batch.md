---
description: Mark a batch shipped in docs/BUILD_PLAN.md — flip its `- [ ]` checkbox to `- [x]` and stamp today's date. Invoked as `/strike-batch <N>` (batch number). Usually called by /phase-closeout, but safe to run standalone.
---

You are striking a batch as shipped in **The Coupon**'s `docs/BUILD_PLAN.md`.

`$ARGUMENTS` is a single batch number matching `^\d+$`.

## Steps

1. Locate the row:
   ```bash
   grep -nE "^- \[[ x]\] \*\*Batch $ARGUMENTS " /Users/craigrobinson/the-coupon/docs/BUILD_PLAN.md
   ```
   If no match → report "Batch $ARGUMENTS not found in BUILD_PLAN.md" and stop. If it's
   already `- [x]` → report already struck and stop (don't double-stamp).

2. Edit that row: change the leading `- [ ]` to `- [x]` and append ` ✅ <today UTC YYYY-MM-DD>`
   immediately after the `**Batch N — <Title>**` (before the ` — <description>`). Use the exact
   line as the Edit anchor; don't touch other rows.

3. Report the struck row back to the user.

## Rules
- BUILD_PLAN.md is the single batch source of record — there is no other batch file.
- Only strike a batch whose work is actually merged to `main` and green (that's the caller's
  responsibility; `/phase-closeout` guarantees it).
- Never invent or renumber batches.

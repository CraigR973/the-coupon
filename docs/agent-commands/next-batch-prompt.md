---
description: Generate the next-batch copy-paste prompt for The Coupon. Reads docs/BUILD_PLAN.md's batch checklist, takes the first un-ticked `- [ ]` row as the next batch, and emits a self-contained prompt. Mechanical — never invent a batch or acceptance criteria.
---

You are generating the paste-prompt for the next session of **The Coupon**.

## Step 1 — Find the next batch

```bash
grep -nE "^- \[[ x]\] \*\*Batch [0-9]" /Users/craigrobinson/the-coupon/docs/BUILD_PLAN.md
```

The **first `- [ ]` (unchecked) row** is the next batch. Capture its number, title, and the
full description (that text IS the scope — there is no separate acceptance doc). If every row
is `[x]`, report "All batches shipped — see BUILD_PLAN Verification for the final pass" and stop.
Never invent a batch number.

## Step 2 — Pull gotchas from the previous batch's session-log entry

```bash
grep -nE "^## Batch [0-9]" /Users/craigrobinson/the-coupon/session-log.md | tail -1
```

Read that entry's "Key facts for future sessions" bullets — carry the still-relevant ones
into the prompt so the next session doesn't rediscover them.

## Step 3 — Assemble the prompt

Emit exactly this shape (fill the placeholders; keep it tight):

```
Build **Batch <N> — <Title>** of The Coupon.

First read `HANDOFF.md`, `STATUS.md`, and `docs/BUILD_PLAN.md` (the batch checklist is the
source of record). Toolchain: this repo has no venv of its own — use app-starter's venv
(`/Users/craigrobinson/app-starter/apps/api/.venv/bin/{ruff,mypy,python}`) with
`PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api`; DB checks use the pip `pgserver`
package. `app-starter` is the infra reference.

Scope (from BUILD_PLAN):
<paste the batch's full description verbatim>

Acceptance / verification (from BUILD_PLAN "Verification"):
<paste the relevant Verification bullets for this batch — e.g. Batch 2 = the Betfair-adapter
pytest bullet; Batch 3 = Pick-uniqueness + scoring + combined-acca; etc.>

Carry-over notes from Batch <N-1>:
- <still-relevant gotchas from the last session-log entry, or "none">

Work on a `feat/` branch. Ship tests with the batch. When green, stop and wait for
`/phase-closeout <N>` — do not auto-close-out.
```

## Rules
- Quote scope/acceptance from `docs/BUILD_PLAN.md`, never from memory.
- The model tag is the user's call (🟢 Sonnet default / 🔴 Opus for scoring, scheduler,
  Betfair sync, bracket-style logic) — suggest, don't hardcode.
- Never include date/commit hashes as a header — those live in session-log entries.

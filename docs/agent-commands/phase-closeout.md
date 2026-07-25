---
description: Run The Coupon's phase close-out — verify green locally, ff-merge the batch's feature branch to main, tick the batch in docs/BUILD_PLAN.md, append a lean session-log entry. Local-only for now (no git remote / CI / staging exist yet — those are gated to launch). Invoked as `/phase-closeout <N>` where N is the batch number (1–6).
---

You are running close-out for **The Coupon**. The user invokes it as:

```
/phase-closeout 1        # close out Batch 1
```

`$ARGUMENTS` is a single batch number matching `^\d+$` (the `Batch N` row in
`docs/BUILD_PLAN.md`). Reject anything else.

> **This repo is local-only right now.** There is no git remote, no CI, and no
> staging/production — its own GitHub remote + Supabase/Railway/Vercel are gated to
> launch (see BUILD_PLAN "Out of scope"). So close-out here means: run the green gate
> locally, ff-merge to **local** `main`, and update docs. The two 🚩 REMOTE-TODO notes
> below mark exactly where `push` / CI-poll / deploy steps slot in once that infra exists.

This is the canonical tool-agnostic command. The `.claude/commands/phase-closeout.md`
wrapper and any other agent should read this file and follow it literally.

## Pre-conditions

1. Current branch:
   `git -C /Users/craigrobinson/the-coupon symbolic-ref --short HEAD`

2. **Green gate (this is the CI stand-in).** Confirm the batch is verified green locally.
   Ask the user `"Ran ruff + ruff format + mypy + pytest locally and all green? (y/N)"`,
   OR run them yourself (see AGENTS/CLAUDE "toolchain" — app-starter's venv + PYTHONPATH):
   - `ruff check src tests` · `ruff format --check src tests` · `mypy src` · `python -m pytest -q`
   - If the batch touched models/migrations, also confirm the migration applies on a
     scratch `pgserver` Postgres. Anything not green → stop.

3. Work is committed to a **feature branch** (`feat/…`/`fix/…`/`chore/…`), not `main`,
   with a clean worktree:
   `git -C /Users/craigrobinson/the-coupon status --porcelain`
   Unrelated untracked scratch files outside the batch may be ignored.

   **Recovery path:** if you're on `main` with uncommitted batch work and the user says
   "do it for me" / "recover it", create the branch and commit the batch's files only
   (never unrelated scratch):
   ```bash
   git -C /Users/craigrobinson/the-coupon checkout -b feat/<batch-slug>
   git -C /Users/craigrobinson/the-coupon add <explicit batch files>
   git -C /Users/craigrobinson/the-coupon commit -F /tmp/msg.txt
   ```

## Steps

### Step 1 — 🚩 REMOTE-TODO: push + poll CI
Skipped while local-only. Once a GitHub remote + Actions exist: push the feature branch,
then poll the run for `head_sha=$(git rev-parse HEAD)` non-blocking (one immediate check,
then at most two ~180s background polls — never a foreground loop). Stop on failure.
For now, Step 0's local green gate is the whole gate.

### Step 2 — Merge the feature branch to main (local, ff-only)

```bash
BRANCH=$(git -C /Users/craigrobinson/the-coupon symbolic-ref --short HEAD)   # capture BEFORE checkout
git -C /Users/craigrobinson/the-coupon checkout main
git -C /Users/craigrobinson/the-coupon merge --ff-only "$BRANCH"
```

If `--ff-only` fails (main moved), stop and report — never force, never auto-resolve conflicts.
🚩 REMOTE-TODO: once a remote exists, follow with `git push origin main` (and, when a
staging/prod split is introduced, land on `staging` first and gate promotion behind `/ship-prod`).

### Step 3 — Tick the batch in docs/BUILD_PLAN.md

Invoke `/strike-batch $ARGUMENTS` (or inline its logic): flip the batch's `- [ ]` to `- [x]`
and append ` ✅ <today UTC YYYY-MM-DD>` to the `**Batch N —` row. If already `[x]`, skip.

### Step 4 — Append a lean session-log entry

Append a NEW section to the bottom of `session-log.md` (repo root) using this template.
Pull commit hashes from `git -C /Users/craigrobinson/the-coupon log main --oneline -<N>`
(the feature commits just merged, before the docs commit you're about to make):

```
---

## Batch N — Title
**Commits:** <hash>[, <hash>] · verified: ruff · mypy · pytest[ · migration/e2e]

### Key facts for future sessions
- <only non-obvious gotchas a future session can't get from the code or `git log`>
- <max ~6 bullets>

**Next:** Batch N+1 — Title   ← the next `[ ]` row in docs/BUILD_PLAN.md
```

Keep it under ~15 lines. No "files modified" / "what shipped" — recoverable from `git show --stat`.

### Step 5 — Commit the docs changes

```bash
git -C /Users/craigrobinson/the-coupon add docs/BUILD_PLAN.md session-log.md STATUS.md
git -C /Users/craigrobinson/the-coupon commit -m "docs: close out Batch $ARGUMENTS — tick BUILD_PLAN + session log"
```

(Also stage STATUS.md if you refreshed its "Now" pointer.) 🚩 REMOTE-TODO: `git push origin main` once a remote exists.

### Step 6 — Report

- Batch closed: N
- Feature commit(s): <hashes>
- Docs commit: <hash>
- BUILD_PLAN row ticked: Batch N ✅
- Verified: ruff · mypy · pytest[ · migration/e2e]  (local gate — no CI yet)
- Next: run `/next-batch-prompt` for the next session's paste-prompt

## Rules

- Never `git push --force` / `--no-verify`; never amend; never skip hooks.
- If anything fails mid-flow, stop and report the exact failure — let the user decide.

# Agent Commands

Canonical command workflows for The Coupon (Claude Code + Codex). Slash-command
wrappers live in `.claude/commands/`, but the source of truth is here.

## Normal batch flow

```text
/next-batch-prompt          # reads the first `- [ ]` row in docs/BUILD_PLAN.md
<implement the batch on a feat/ branch, with tests, until green>
/phase-closeout <N>         # verify green locally → ff-merge to main → tick BUILD_PLAN + session-log
```

Invariant: implementation happens on a `feat/` branch, never directly on `main`.
`/phase-closeout` recovers from dirty `main` only when the user explicitly asks.

**Batch source of record:** `docs/BUILD_PLAN.md` (a `- [ ]`/`- [x]` checklist).
**Local-only right now:** no git remote / CI / staging-prod yet — the green gate is local
and close-out ff-merges to local `main` (see the 🚩 REMOTE-TODO markers in `phase-closeout.md`).

## Commands (Coupon-ready)

- `next-batch-prompt.md` — emit the next session's prompt from `docs/BUILD_PLAN.md`.
- `phase-closeout.md` — local green gate → ff-merge to `main` → tick BUILD_PLAN + session-log.
- `strike-batch.md` — flip a batch's checkbox to `- [x]` in `docs/BUILD_PLAN.md`.

## ⚠️ Not yet reconciled (calcio leftovers)

`batch-start.md`, `batch-verify.md`, `ship-staging.md`, `ship-prod.md` are still calcio's —
they hardcode the `wc_2026_predictor` repo path and assume a remote/CI/staging that this repo
doesn't have yet. Don't rely on them. Reconcile (or delete) them in the Batch-6 rebrand, or
when launch infra lands. `AGENTS.md` (repo root) is likewise still calcio, under a stale banner.

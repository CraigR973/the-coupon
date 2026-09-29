# 07 — Agent delivery pipeline

The application ships no LLM features, so this lens points at what does use AI: **agents
build this repository, and a green batch closes out automatically, including the push to
`main` that Vercel deploys to members.** Batches 120-168, 95 and 115 — 130 commits since
`2ce6f42` — all went out that way. This pass audited what the agents *did*, not only the
rules they were given.

## Method

Everything below was run on 28-29 Sep 2026 against `main` at `eb18bcb`, which production
serves (web and API in sync per the lead's drift check), so every finding is **live**.

- **What the agents did.** Every commit since `2ce6f42` was listed with the main-branch
  reflog (which records the branch each merge came from), classified API / web / tooling
  with the close-out guard's own path rules, and scanned hunk by hunk for skip, xfail,
  `.only`, `.todo`, `type: ignore`, `eslint-disable`, `noqa`, removed test functions,
  removed or changed assertions and ratchet changes. Every hit was read by hand.
- **The guards, replayed.** In a push-less scratch clone, for each of the 55 non-docs
  commits, local `main` was set to its parent and the guardrail and close-out guard were run
  **as they existed at that commit** (the drift check stubbed, since the real one calls
  production).
- **The gate, attacked.** In a throwaway worktree (`throwaway/pipeline-probe`, never
  pushed): 24 single weakenings against the guardrail, five checks that unprotected config
  files change what ruff, mypy, eslint, vitest and pytest enforce, a self-approval probe on
  a batch-named branch (in the clone, to keep `feat/batch-*` refs out of the shared
  repository), and one full `SKIP_PROD_BUNDLE=1` gate over six simultaneous weakenings.
- **CI.** Read-only `gh run list` / `gh run view` for every run since 20 Sep; branch
  protection and rulesets read through `gh api`.
- **Documents.** Byte counts of exactly what `/next-batch-prompt`, `/batch-start` and
  `/group-start` instruct an agent to read; a contradiction sweep across `AGENTS.md`,
  `CLAUDE.md`, `docs/agent-commands/*`, `.claude/`, `.codex/`, `ci-local.sh`, `STATUS.md`
  and the head of `docs/BUILD_PLAN.md`.
- The local agent configuration was read for **structure only**; no value, key or project
  reference was copied.

Scripts and raw output: `notes/07-pipeline/`.

## Prior findings

| id | batch | status | evidence |
| --- | --- | --- | --- |
| PIPE-01 | owner, by hand | **not fixed** | PENDING-TABLE |

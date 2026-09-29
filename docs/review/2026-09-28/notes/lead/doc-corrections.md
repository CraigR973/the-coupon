# Doc-only corrections applied on this branch

Applied by the lead on 29-30 Sep, as the prompt asks (the 2026-09-13 review listed its
corrections and left them). Each line: file — from → to — who found it.

| file | change | found by |
| --- | --- | --- |
| `AGENTS.md` | "520 Postgres-backed tests" → 550; "780 passed, 520 skipped (2026-09-24, 1,300 tests)" → "800 passed, 550 skipped (2026-09-29, 1,350 tests)" | 07 (PIPE-06), measured by 07 |
| `AGENTS.md` | "step 8's push" and "Step 8 pushes `main`" → step 9 (Batch 152 inserted the safety step) | 07 |
| `AGENTS.md`, `docs/agent-commands/README.md` | `/group-start <I-Y>` → `<I-Z>` (Group Z exists) | 07 |
| `docs/agent-commands/batch-start.md` | "Close-out's own step 8 pushes" → step 9 | lead, same drift |
| `docs/agent-commands/batch-verify.md` | no-database split → 800 / 550 (2026-09-29); the single-file mypy/pytest commands pointed at app-starter's venv, which `AGENTS.md` says cannot collect the suite → the gate's own venv | 07 |
| `docs/agent-commands/phase-closeout.md` **(protected file)** | no-database split → 800 / 550; deleted the stale "For Batch 6 this also includes browser screenshots" | 07 |
| `STATUS.md` | web line: "last live-verified at `b08a47f3` (2026-09-27)" → serves `4121cf0`, checked by stylesheet 2026-09-28 (lead); "certified worst day is 481" → what 481 covers and omits, and the measured 289 (04); toolchain: the ratchet stated twice and the 780/520 split → one statement and 800/550 (07); Vercel CLI line notes Node 20 is end-of-life (04, OPS-19) | lead, 04, 07 |
| `docs/LAUNCH_PLAN.md` | "Revisit post-launch." → revisited by Batch 95, built and off; L5 "restoring one is Batch 95" → Batch 95 built it, switched off | 05 |
| `docs/review/2026-09-13/08-sequencing.md` | SEC-22 "Folded into Batch 127" → planned for 127, which left it out; see SEC-30 | 01 |
| `docs/BUILD_PLAN.md` | the seven ticked rows under "Open batches" (115, 140, 148-151, 168) moved into `## Closed batches` at their written positions, content unchanged (verified by a sorted-line diff) | 07 (PIPE-18) |
| `docs/BUILD_PLAN.md`, Batch 123 row | added a dated note that its API half does not hold (SEC-28) | 01 |
| `screenshots/INDEX.md` (lens 03 rows) | 26 "happy"/"firstrun" captures of six screens were taken with the browser still offline; each row now says so and points to lens 06's `*-l06--*` re-capture | 06 |
| `notes/07-pipeline/scan-test-diffs.txt` | one redacted member name replaced, and this branch's history rewritten so no commit carries it | 01 |

**Consequence to know before merging:** `phase-closeout.md` is on the guardrail's
protected list, so `scripts/ci-local.sh` run *on this branch* fails its first check. The
change is a stale number and a stale sentence. On `main` after a merge there is nothing to
flag.

**Not applied — code, so they belong to batches:** `apps/api/src/config.py:113-114` comment
("460 of 500" → 481) and `services/football_data.py:935` docstring ("three queries for a
slate of any size" — wrong, PERF-18).

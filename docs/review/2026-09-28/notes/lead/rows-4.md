- [ ] **Batch 198 — The gate is judged by the branch's own copy of the gate**
  — specified from `docs/review/2026-09-28/07-agent-pipeline.md`, PIPE-10 and PIPE-11 (MED,
  live, verified; PIPE-04 partial). `ci-local.sh` runs the guardrail from the working tree, and
  the guardrail's protected list and approval table live inside it: prepending `exit 0` passes;
  a batch branch can add its own approval line; new `mypy.ini`, nested `.eslintrc`, `ruff.toml`,
  `vitest.config.ts` or three lines of `conftest.py` each switch a check off. A full gate over six
  simultaneous weakenings passed with the exact ratchet counts. On 22 Sep the protected smoke
  script changed three times on `fix/` branches the guardrail refuses, with no record of who
  approved it. No batch since 2ce6f42 abused any of this.

  Run the guardrail and the count check from `main`'s copy (`git show main:…`); read the approval
  table from `main` and require the approving row to quote the file list; protect by pattern
  (`**/conftest.py`, `**/pytest.ini`, `**/mypy.ini`, `**/ruff.toml`, `**/setup.cfg`,
  `**/.eslintrc*`, `**/.eslintignore`, `**/vitest.config.*`, `**/tsconfig*.json`,
  `check-migration-recovery.sh`, `AGENTS.md`); make close-out refuse to push a tree without a
  matching gate-pass stamp.

  **Owner-approved gate maintenance is required** — this batch edits the guardrail and
  `ci-local.sh`, which the guardrail protects. Record the approval in the guardrail before
  starting (as for 153 and 127).

  Verification: rehearse each of the lens's 24 weakenings and the six-at-once gate — all
  refused; a legitimate batch passes; a push without a stamp is refused.

  Scope boundary: the guardrail, the count check, the push precondition. **Tooling-only.**

- [ ] **Batch 199 — CI goes red, close-outs push on red, and nothing reads it**
  — specified from `docs/review/2026-09-28/07-agent-pipeline.md`, PIPE-12 (MED, live, verified).
  8 of 72 runs on `main` since 20 Sep failed (confirmed by the lead with `gh run list`):
  Batches 120-122 closed out and pushed while CI was red; two backend flakes
  (`test_durable_rate_limit::test_an_unknown_name_is_charged_…`, a `uq_leagues_join_code`
  collision in `test_scheduler_jobs`) are recorded nowhere. CI runs fewer checks than the local
  gate (no guardrail, no ratchet, no zero-skip), `main` has no branch protection, and
  `phase-closeout.md` says "Do not poll CI".

  **Owner decision** (README decision 6; recommended: yes). After the push, close-out waits for
  the run on the pushed SHA and writes its conclusion into the session-log line; red stops a
  group and is treated as red `main`. Add the guardrail and the count check to CI; fix both
  flakes.

  Verification: a rehearsal where a red CI run stops the next batch; CI refuses a skipped test
  and a lowered ratchet; both flakes pass 50 consecutive runs.

  Scope boundary: close-out's CI step, CI's checks, two tests. **Tooling-only — owner-approved
  gate maintenance (edits `phase-closeout.md` and `.github/workflows/ci.yml`).**

- [ ] **Batch 200 — The only end-to-end journey runs outside the gate**
  — specified from `docs/review/2026-09-28/07-agent-pipeline.md`, PIPE-13 (MED, live, verified).
  `apps/web/e2e/coupon-flow.spec.ts` — unique claims, lock, settle, standings through the real
  bundle and API — runs in neither `ci-local.sh` nor CI. It broke on 23 Sep (Batches 139 and
  157) and stayed broken five days; Batch 149 pushed before running it, and the toast defect it
  then found was live for about 23 minutes.

  Run the journey in `ci-local.sh` and CI (58 s measured; it needs the seeded e2e server and
  `FRONTEND_ORIGIN`), on its own port with the strict-port pattern Batch 152 established.

  Verification: the gate fails when the journey fails; a rehearsal that breaks the pick flow
  is caught.

  Scope boundary: running the existing journey. **Tooling-only — owner-approved gate
  maintenance (`ci-local.sh`, `ci.yml`).**

- [ ] **Batch 201 — The split-half refusal is cleared by a flag with no record, and a two-batch split passes it**
  — specified from `docs/review/2026-09-28/07-agent-pipeline.md`, PIPE-14 (MED, live, verified;
  PIPE-05 partial). Replayed, the close-out guard refuses all seven API+web batches since
  2ce6f42, but only 136 and 148 have a record of the owner scheduling the shipment;
  `--shipment-scheduled` is a plain argument. And the guard only *reports* existing drift: a
  web-only batch whose route an earlier API-only batch added passes while `/ship-prod` is owed.

  Write a "Close-out safety:" line into every session-log entry naming the guard's verdict
  and, for a split-half batch, who scheduled the shipment and when; refuse a web change while
  drift reports a shipment owed unless the same acknowledgement is given.

  Verification: rehearsals of both shapes refused without the acknowledgement and recorded
  with it.

  Scope boundary: the close-out guard and its record. **Tooling-only — owner-approved gate
  maintenance (`check-closeout-safety.sh`, `phase-closeout.md`).**

- [ ] **Batch 202 — The toolchain behind the build is two to four majors behind, with 32 advisories**
  — specified from `docs/review/2026-09-28/01-security.md` SEC-30 (LOW; SEC-22 not fixed) and
  `04-performance-operations.md` OPS-15 (LOW) and PERF-22 (LOW). SEC-22 was "folded into Batch
  127", which then left OPS-15 out, so nothing carried it: 32 npm advisories across 17 build and
  test packages (none in the shipped bundle). Vite 5 → 8, ESLint 8 → 10, Tailwind 3 → 4, Vitest
  2 → 5 are current. `framer-motion` is still a declared dependency though nothing imports it.

  **Owner decision** (README decision 8): refresh, or record an explicit acceptance. If
  refreshed, one major at a time with the gate green after each, and drop `framer-motion`.

  Verification: OSV re-run clean of build-tool advisories; the full gate green; bundle bytes
  and Lighthouse unchanged or better.

  Scope boundary: the web toolchain. **Tooling — owner-approved (`apps/web/package.json` is
  protected).**

- [ ] **Batch 203 — Pipeline and operations hygiene**
  — specified from `docs/review/2026-09-28/07-agent-pipeline.md` PIPE-15, PIPE-16, PIPE-17,
  PIPE-19 and `04-performance-operations.md` OPS-19 (all LOW or INFO). Follow-ups agents write
  in the session log become nobody's work (the review has turned today's into rows). Batch 161
  added ten tests true by construction. The stop hook is silent on a dirty batch branch — the
  moment close-out is decided — and speaks on branches with no batch. `claude.yml` is template
  residue with `contents: write` in a public repository (inert: no secrets, every run skipped);
  `pyproject.toml` pins fastapi 0.111.0 and starlette 0.37.2 the gate does not use; the drift
  probe still names Batch 51. `ship-prod.md` runs the Railway and Vercel CLIs on Node 20 in nine
  places, including both rollback commands.

  Add a "Follow-ups" section to the session-log template that close-out copies into rows;
  rewrite 161's tautologies to assert behaviour; fire the hook on the batch branch; delete
  `claude.yml`; drop the stale pins; point the drift probe at a recent route; re-test both CLIs
  on Node 24 and update `ship-prod.md` and STATUS together.

  Verification: each item checked; both rollback commands rehearsed on Node 24 against
  staging.

  Scope boundary: these hygiene items. **Tooling-only (`phase-closeout.md` edits need
  owner-approved gate maintenance).**

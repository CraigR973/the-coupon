# 07 — Agent delivery pipeline

The application ships no LLM features, so this lens points at what does use AI: **agents
build this repository, and a green batch closes out automatically, including the push to
`main` that Vercel deploys to members.** Batches 120-168, 95 and 115 — 130 commits since
`2ce6f42` — all went out that way. This pass audited what the agents *did*, not only the
rules they were given.

**The short version.** The agents behaved well: across 55 code commits there is no new
skip, xfail or `.only`, every changed test expectation was specified by its row and
reported, and the one oracle change (Batch 131) stopped for the owner as the run order said
it would. The machinery around them is weaker than it looks. The gate judges each batch
with **that batch's own copy of the gate**, so it can be switched off from inside the
branch; it was changed three times on its first day on branches the guardrail refuses; CI
went red eight times in a week and nothing reads it; and the one end-to-end journey is
outside the gate and rotted for five days.

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

Scripts and raw output: `notes/07-pipeline/` (`replay_guards.sh`, `gate_probes.sh`,
`precedence_probes.sh`, `self_approval_probe.sh`, `combined_weakening.py`,
`scan_test_diffs.py`, and a `*-output.txt` beside each).

## Prior findings

| id | batch | status | evidence |
| --- | --- | --- | --- |
| PIPE-01 | owner, by hand | **not fixed** | `.claude/settings.local.json` unchanged since 30 Jul: `Bash(*)`, `mcp__supabase__execute_sql` allowed, `rm -rf` rules for other repositories, `enableAllProjectMcpServers: true`. `.mcp.json` binds the Supabase server to a project that is neither the staging project in `.codex/config.toml` nor production, with no read-only flag (compared by equality, never printed). **Driven:** this review's own session was offered the whole Supabase tool family — `execute_sql`, `apply_migration`, `delete_branch`, `merge_branch`, `deploy_edge_function` — and did not call it |
| PIPE-02 | 153 | **partial** | Both hooks now say close out automatically (identical commands, `.claude/settings.json` = `.codex/hooks.json`). Re-driven in the worktree: the hook is **silent on a dirty batch tree**, which is the state at the close-out decision (the diff is uncommitted until close-out step 4), and speaks on any clean non-main branch — including a review branch with no batch. See PIPE-17 |
| PIPE-03 | 152 | PENDING | |
| PIPE-04 | 152 | **partial** | Counts are recorded and ratcheted, and a fall, a skip or an xfail fails the gate; lowering the ratchet is refused (probe G03). But a loosened assertion, a swapped-in trivial test, `type: ignore`, `eslint-disable`, `.todo`, and five unprotected config files all pass — and the guardrail can be switched off from the branch. See PIPE-10 |
| PIPE-05 | 152 | **partial** | Replayed: the guard as it stood refuses all seven API+web batches (123, 124, 143, 156, 157, 136, 148) and passes the other 48. Drift now runs before the push. But existing drift is only reported: a web-only batch over an owed `/ship-prod` passes (probe). See PIPE-14 |
| PIPE-06 | 153 | **partial** | Figures now carry dates, as the fix asked; they have drifted again — "780 passed, 520 skipped" at 1,300 tests in `AGENTS.md`, `batch-verify.md` and `phase-closeout.md` against a ratchet of 1,350 — and `AGENTS.md` still sends agents to "step 8's push", which is step 9 since Batch 152 inserted the safety step. PENDING-NODB |
| PIPE-07 | 154 | **held**, with a leak | `/next-batch-prompt` reads **38.3 KB** today (Batch 154 said 38 KB). But 14.7 KB of the 18.8 KB build-plan head is seven *ticked* rows, because nothing moves a row out when it closes. See PIPE-18 |
| PIPE-08 | 155 | **held** | Every proper-noun token Batch 155 removed has **zero** hits on `main` (checked by hashing, never printed). History was not rewritten, per the owner's decision |
| PIPE-09 | 127 | **held** | `ci-local.sh`'s pnpm check evaluated verbatim with a pnpm 9.14.2 shim first on `PATH`: refused, exit 1, "package.json pins '9.15.0'" |

**Tally: 3 held, 5 partial, 1 not fixed, 0 regressed.** PENDING-TALLY

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| PIPE-10 | MED | live | verified | The gate is judged by the branch's own copy of the gate, and five unprotected config files switch its checks off |
| PIPE-11 | MED | live | verified | The protected smoke script was changed three times on branches the guardrail refuses, with no record |
| PIPE-12 | MED | live | verified | CI went red eight times in a week, three batches deployed on red, and nothing reads it |
| PIPE-13 | MED | live | verified | The only end-to-end journey is outside the gate; it rotted for five days and one batch deployed before running it |
| PIPE-14 | MED | live | verified | The split-half refusal is cleared by a flag with no durable record, and a two-batch split passes it |
| PIPE-15 | LOW | live | verified | Follow-ups agents record in the session log become nobody's work |
| PIPE-16 | LOW | live | verified | The ratchet counts tests, not what they check — and one batch padded it with tautologies |
| PIPE-17 | LOW | live | verified | The stop hook is silent at the close-out decision and speaks on branches with no batch |
| PIPE-18 | LOW | live | verified | Closed rows stay in the build plan's "Open batches" head, which is 78% closed rows |
| PIPE-19 | INFO | live | verified | Dormant or stale agent machinery: an issue-driven workflow, stale metadata, an orphaned worktree |

## PIPE-10 · MED · live · verified — the gate is judged by the branch's own copy of the gate

`ci-local.sh` runs `scripts/assert-quality-guardrails.sh` **from the working tree**, and the
guardrail's list of protected files and its table of owner approvals both live inside that
same file. So the thing being judged supplies the judge. Driven in the throwaway worktree
and the scratch clone:

| probe | guardrail |
| --- | --- |
| edit `pyproject.toml` ruff or mypy settings, `.eslintrc.cjs`, `tsconfig.json`, `ci-local.sh`, `phase-closeout.md`, `check-closeout-safety.sh`; lower the ratchet | **refused** (G03, G07-G11, G13, G21) |
| prepend `exit 0` to the guardrail itself | **passes, silently** (G12) |
| on `feat/batch-999-probe` with an open row, add a `999)` line approving `ci-local.sh` and the guardrail | **passes**, printing "Batch 999's owner-approved gate maintenance changes"; refused once the row is ticked |
| add `apps/api/mypy.ini` with `ignore_errors = True` | passes — and a real type error in `src` then passes mypy (was exit 1, now 0) |
| add `apps/web/src/.eslintrc.json` turning a rule off | passes — and an `any` that failed lint then passes |
| add `apps/api/ruff.toml` (`line-length = 100`, `select = ["E"]`) | passes — and an unused local that failed ruff then passes |
| add `apps/web/vitest.config.ts` | passes — and vitest uses it instead of `vite.config.ts` |
| add three lines to `tests/conftest.py` (`pytest_pyfunc_call` returning `True`) | passes — and "1 failed, 9 passed" becomes "10 passed", count unchanged |
| add `pytest.ini`, `.eslintignore`; edit `check-migration-recovery.sh`, `AGENTS.md`, `batch-start.md` | passes (G19, G22-G24) |
| loosen an assertion in place, `# type: ignore`, `eslint-disable` | passes (G04-G06), by design — the guardrail checks files, not content |

PENDING-COMBINED

The self-approval route is not hypothetical: it is how the approval table arrived. Batch
153's own branch added `153) … scripts/assert-quality-guardrails.sh` and the modified
guardrail then approved its own modification (`eabe49d`). The owner had approved that one
in the row; the script cannot tell, because it checks only that the row is open, not that
an approval is written in it. The comment asking agents not to add entries "on an agent's
own judgement" is the only control.

Before rating this, the pass tried to disprove it: every probe was re-run from a clean tree,
the precedence checks were run with the tools exactly as `ci-local.sh` invokes them, and the
control (ticked row) was refused. What keeps it MED rather than HIGH: none of the 55 code
commits since `2ce6f42` did any of this — the agents' record is clean (see "Checked and found
nothing material") — and each route is a deliberate edit that would show in the diff the
owner reviews after the deploy.

**Impact on a member:** an agent under pressure to reach green can turn a check off from
inside its own branch, and the fault it was hiding deploys to members on the close-out push.

**Fix:** run the guardrail and the count step from `main`'s copy (`git show
main:scripts/assert-quality-guardrails.sh | bash`), so a branch's gate edits only take effect
after merge; move the approval table out of the branch's reach (read it from `main`, and
require the approving row to quote the file list); protect by pattern, not by name —
`**/conftest.py`, `**/pytest.ini`, `**/mypy.ini`, `**/.mypy.ini`, `**/ruff.toml`,
`**/.ruff.toml`, `**/setup.cfg`, `**/.eslintrc*`, `**/.eslintignore`, `**/vitest.config.*`,
`**/tsconfig*.json` — plus `check-migration-recovery.sh` and `AGENTS.md`.

## PIPE-11 · MED · live · verified — the gate was changed three times on branches the guardrail refuses

On 22 Sep, hours after Batch 152 made `scripts/run-prod-bundle-smoke.sh` a protected file,
three branches changed it: `fix/deterministic-delivery-gates` (`d1b9ee9`, which also moved
three `test_round_population` windows off a fixed Tuesday), `fix/preview-readiness-signal`
(`7ef953d`) and `fix/preview-readiness-ansi` (`89217f8`). Replaying the guardrail as it stood
at each commit, in the scratch clone, **refuses all three** — none is a batch branch and no
approval existed — so a green `ci-local.sh` cannot have run on them. All three were merged to
`main` and pushed, which deploys. None has a commit body, a `BUILD_PLAN` row or a
`session-log.md` entry, and unlike 101 of the 130 commits they carry no agent trailer, so it
is not recorded whether an agent or the owner made them.

The changes themselves look right — a longer readiness wait, running Vite directly because
GitHub's pnpm wrapper buffered its output, and tolerating ANSI colour in the readiness line
— and the third one turned CI green (PIPE-12). The finding is the process: on the gate's
first day, its protected file changed three times with no record of who approved it.

A smaller instance of the same looseness: Batch 144's ratchet raise (1,282 → 1,285) is in
its close-out *documents* commit (`9a1467e`), not the batch commit, so `1bfe512` on its own
fails its own gate; close-out step 8 says to stage the three documents only.

**Impact on a member:** the check that stands between a batch and members can be changed
with nothing but the diff to show it happened.

**Fix:** make the push conditional on a gate pass for the exact tree being pushed —
`ci-local.sh` writes the tree hash on PASS, and close-out (and any push) refuses without a
matching stamp; a red-`main` fix that touches a protected file is owner-approved gate
maintenance with a row, like 153 and 127.

## PIPE-12 · MED · live · verified — CI goes red, three batches deployed on red, and nothing reads it

`gh run list` since 20 Sep: **8 of 72 runs on `main` failed.**

| when (UTC) | commit | failed | then |
| --- | --- | --- | --- |
| 22 Sep 11:30 → 21:06 | `c7a50bb` (152 close-out), `a689a57` (120), `48b6627` (121), `0ff3e8c` (122), `d1b9ee9`, `7ef953d` | prod-bundle smoke, six in a row | green at `89217f8`, 21:17 |
| 23 Sep 02:41 | `ac54a71` (143 close-out) | `test_durable_rate_limit.py::test_an_unknown_name_is_charged_even_though_the_handler_commits_nothing` — 401 where 429 was expected | next push green |
| 23 Sep 22:09 | `bf97763` (128 close-out) | `test_scheduler_jobs.py::test_home_and_the_coupon_pick_the_same_round_in_every_state` — `uq_leagues_join_code` unique violation | next push green |

So Batches 120, 121 and 122 — the claim race, the stray round and the PIN takeover — were
closed out and deployed while CI was red, and the group carried on. The two backend failures
are flakes: each passed on the next push, **neither is mentioned anywhere** in
`session-log.md`, `STATUS.md` or `BUILD_PLAN.md`, and neither test has been touched since.
Batch 149 met two more locally — "timed out in two unrelated existing tests", rerun to green,
unnamed.

This is structural, not negligence. `phase-closeout.md` says "Do not poll CI". Close-out never
pushes a feature branch, so CI only ever runs *after* the push that deploys. CI runs fewer
checks than the local gate — no guardrail, no ratchet, no zero-skip check — so it would pass
a skipped suite. `main` has no branch protection (`gh api …/branches/main/protection` → 404,
no rulesets), so nothing mechanical stops a force-push either.

**Impact on a member:** a fault that only CI's clean Linux/UTC run exposes — the class
`vite.config.ts` pins `America/New_York` to catch — reaches members and stays, because the
only signal goes to an inbox nobody is asked to read.

**Fix:** after the push, close-out waits for the run on the pushed SHA (`gh run watch`,
about 7-8 minutes) and writes its conclusion into the session-log line; red stops a group
and is treated as red `main`. Add the guardrail and the count check to CI. Fix the two flaky
tests (the join-code collision looks like two random codes meeting in a committed table).
This reverses a written instruction, so it is an owner decision below.

## PIPE-13 · MED · live · verified — the only end-to-end journey is outside the gate

`apps/web/e2e/coupon-flow.spec.ts` is the one test that registers members, picks, settles
and reads standings through the production bundle. Neither `ci-local.sh` nor CI runs it:
`playwright.prod-bundle.config.ts` matches `prod-bundle*.spec.ts` only, and the journey is
`pnpm e2e`, run by hand.

It rotted. Batch 139 (23 Sep 01:34) opened the first competition by default, and the journey
still asserted no pick card was visible; Batch 157 (23 Sep 17:15) removed "Averaged over 1 of
your 2 leagues", which the journey still expected. Both batches closed green. The journey was
repaired five days later by `83facaf` (28 Sep), an out-of-batch commit with no session-log
entry of its own. For those five days a batch that broke register → pick → settle would have
deployed on a green gate.

Group Z then leaned on it as evidence ("production-bundle coupon journey passed" in four
session-log headers), and Batch 149 shows the ordering problem: it closed out and pushed at
20:54, *then* ran the seeded journey, which found the phone toast offset and a low-contrast
toast title; `4121cf0` fixed them at 21:17. Members had the defect for about 23 minutes.

**Impact on a member:** a regression in the Saturday journey that only the end-to-end run can
see deploys with a green gate.

**Fix:** run the journey in `ci-local.sh` and CI (Batch 149 measured it at 58 seconds; it
needs the seeded e2e server and `FRONTEND_ORIGIN`), or at minimum make it a close-out step
before the push for any batch that touches `apps/web`.

## PIPE-14 · MED · live · verified — the split-half refusal is cleared by a flag, with no record

Replayed as it stood, the close-out guard **refuses** all seven API+web batches since
`2ce6f42`: 123, 124, 143, 156, 157, 136 and 148. The session log records the owner
scheduling the shipment for **136 and 148 only**. For 123, 124, 143, 156 and 157 there is no
durable record of how the refusal was cleared — `--shipment-scheduled` is a plain argument any
agent can type, and the close-out report that should name it exists only in a chat
transcript. (Phases 4 and 6 of the 2026-09-13 run order end "→ `/ship-prod`", which an agent
could read as the schedule.) No member was hurt: all five web halves were written to be
inert against the old API — Batch 124 says so, 157 tests it, 156 reads the new field as
`?? 0` — but that was the agents' judgement, not the guard.

The other gap is the one PIPE-05 was about. The guard judges one batch at a time and only
*reports* existing drift. A probe with drift stubbed to "a `/ship-prod` is owed" and a
web-only diff: **"PASS — web-only batch"**, exit 0. So an API-only batch followed by a
web-only batch that calls its new route deploys the web half against an API that 404s — the
2026-09-13 Calendar-page incident, split across two batches instead of one.

**Impact on a member:** a screen can ship calling a route production does not serve until
someone runs `/ship-prod`.

**Fix:** the session-log template gets the "Close-out safety:" line Group Z already writes by
habit, naming the guard's verdict and, for a split-half batch, who scheduled the shipment and
when; the guard refuses a web change while drift reports a shipment owed, unless the same
acknowledgement is given.

PENDING-SECTIONS-B

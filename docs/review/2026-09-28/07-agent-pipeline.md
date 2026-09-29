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
| PIPE-02 | 153 | **partial** | Both hooks now say close out automatically (identical commands, `.claude/settings.json` = `.codex/hooks.json`). Re-driven in the worktree: the hook is **silent on a dirty batch tree**, which is the state at the close-out decision (the diff is uncommitted until close-out step 4), and on a clean branch with no batch it said to run `/phase-closeout`. See PIPE-17 |
| PIPE-03 | 152 | **held** | Re-driven on port 4291 (4173 is the lead's): the real script with only the port changed, the port held by another server — Vite reported "Port 4291 is already in use" and the smoke failed in one second, "preview failed before readiness (exit 1)", before Playwright ran. Small fragility: the readiness pattern hard-codes `4173` separately from `PORT` |
| PIPE-04 | 152 | **partial** | Counts are recorded and ratcheted, and a fall, a skip or an xfail fails the gate; lowering the ratchet is refused (probe G03). But a loosened assertion, a swapped-in trivial test, `type: ignore`, `eslint-disable`, `.todo`, and five unprotected config files all pass — and the guardrail can be switched off from the branch. See PIPE-10 |
| PIPE-05 | 152 | **partial** | Replayed: the guard as it stood refuses all seven API+web batches (123, 124, 143, 156, 157, 136, 148) and passes the other 48. Drift now runs before the push. But existing drift is only reported: a web-only batch over an owed `/ship-prod` passes (probe). See PIPE-14 |
| PIPE-06 | 153 | **partial** | Figures now carry dates, as the fix asked; they have drifted again — "780 passed, 520 skipped" at 1,300 tests in `AGENTS.md`, `batch-verify.md` and `phase-closeout.md` against a ratchet of 1,350 — and `AGENTS.md` still sends agents to "step 8's push", which is step 9 since Batch 152 inserted the safety step. Re-measured at `eb18bcb` without a database: **800 passed, 550 skipped** (29 Sep, 1,350 tests). |
| PIPE-07 | 154 | **held**, with a leak | `/next-batch-prompt` reads **38.3 KB** today (Batch 154 said 38 KB). But 14.7 KB of the 18.8 KB build-plan head is seven *ticked* rows, because nothing moves a row out when it closes. See PIPE-18 |
| PIPE-08 | 155 | **held** | Every proper-noun token Batch 155 removed has **zero** hits on `main` (checked by hashing, never printed). History was not rewritten, per the owner's decision |
| PIPE-09 | 127 | **held** | `ci-local.sh`'s pnpm check evaluated verbatim with a pnpm 9.14.2 shim first on `PATH`: refused, exit 1, "package.json pins '9.15.0'" |

**Tally: 4 held, 4 partial, 1 not fixed, 0 regressed.** Every "held" was re-driven: PIPE-03 by holding the port, PIPE-07 by measuring, PIPE-08 by grepping `main`, PIPE-09 by running the gate's own pnpm check against the wrong version.

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| PIPE-10 | MED | live | verified | The gate is judged by the branch's own copy of the gate, and five unprotected config files switch its checks off |
| PIPE-11 | MED | live | verified | The protected smoke script was changed three times on branches the guardrail refuses, with no record |
| PIPE-12 | MED | live | verified | CI went red eight times in a week, three batch close-outs pushed on red, and nothing reads it |
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

**Then the whole gate, over six weakenings at once** (`combined_weakening.py`): a core
assertion loosened in place (the installation pick budget now accepts 201 *or* 429); a
backend test deleted and a trivial one added; a test dropped at collection by the
unprotected `conftest.py` and another trivial one added; a real type error in `src` silenced
with `# type: ignore`; a real lint error silenced with `eslint-disable`; a frontend test
swapped for `expect(true).toBe(true)` plus an `it.todo`. `SKIP_PROD_BUNDLE=1
scripts/ci-local.sh` in the worktree, 14:22-14:34 on 29 Sep: **"ci-local: PASS (10
checks)"** — backend 1,350 tests and frontend 1,204, zero skipped, exactly the ratchets.

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

## PIPE-12 · MED · live · verified — CI goes red, close-outs push on red, and nothing reads it

`gh run list` since 20 Sep: **8 of 72 runs on `main` failed.**

| when (UTC) | commit | failed | then |
| --- | --- | --- | --- |
| 22 Sep 11:30 → 21:06 | `c7a50bb` (152 close-out), `a689a57` (120), `48b6627` (121), `0ff3e8c` (122), `d1b9ee9`, `7ef953d` | prod-bundle smoke, six in a row | green at `89217f8`, 21:17 |
| 23 Sep 02:41 | `ac54a71` (143 close-out) | `test_durable_rate_limit.py::test_an_unknown_name_is_charged_even_though_the_handler_commits_nothing` — 401 where 429 was expected | next push green |
| 23 Sep 22:09 | `bf97763` (128 close-out) | `test_scheduler_jobs.py::test_home_and_the_coupon_pick_the_same_round_in_every_state` — `uq_leagues_join_code` unique violation | next push green |

So Batches 120, 121 and 122 — the claim race, the stray round and the PIN takeover — were
closed out and pushed while CI was red, and the group carried on. They were API-only, so the
push itself changed nothing members saw, and CI was green again (through PIPE-11's
out-of-batch fixes) before their `/ship-prod` that night; a web batch in the same position
would have been live on red. The two backend failures
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

## PIPE-15 · LOW · live · verified — follow-ups recorded in the session log become nobody's work

Agents flag what their row does not cover, as they should — and there it stops. Two since
`2ce6f42`, neither with a row, and there are no open rows at all:

- **Batch 138:** UX-18's `opacity-60` payout figure on the pick row — "no batch row currently
  does". Still there: `apps/web/src/components/PickRow.tsx:238`, `lost && 'opacity-60'`.
- **Batch 131:** a member whose only picks were voided now has a `null` win rate, and
  `apps/web/src/pages/PlayerProfilePage.tsx:100` tells them "Nothing has settled yet", which is
  false for them. "Copy is outside this row's scope boundary, so it is left as-is."

**Impact on a member:** small defects an agent found and named stay live indefinitely.

**Fix:** a close-out step — every "not in this batch" or "follow-up" line becomes an unchecked
row, or is marked accepted, before the push. (The lead should cross-check both items against
lenses 02 and 03.)

## PIPE-16 · LOW · live · verified — the ratchet counts tests, not what they check

The count is an exact floor, which catches a deleted or skipped test. It cannot see a test
replaced by a weaker one (the combined gate above swapped two and stayed green), and it
rewards volume. Batch 161 added ten parametrised cases of
`bounded = min(unbounded, installation); assert bounded <= installation` — true by
construction for any input — which is two-thirds of that batch's +15. The behaviour itself is
tested properly elsewhere (the HTTP test that a second league is refused once the deployment's
allowance is spent); the tautologies are padding, not harm.

**Fix:** have close-out print the test IDs removed or renamed against `main` (`pytest
--collect-only -q`, `vitest list`) into the session-log entry, so the owner's after-the-fact
review sees a swap even when the count holds.

## PIPE-17 · LOW · live · verified — the stop hook speaks at the wrong moment

PIPE-02's text fix held: both hooks now tell an agent to close out a green build batch without
waiting. But the hook only speaks when the branch is **clean**. In the automatic flow the
batch's changes stay uncommitted until close-out step 4, so at the moment an agent decides
whether to close out, the tree is dirty and the hook is silent (re-driven in the worktree:
no output). It does speak on any clean non-main branch, including a review branch with no
batch on it: on the clean throwaway branch it printed "run /phase-closeout <id> without
waiting to be asked". An agent on a review or chore branch is being told to push `main`.

**Fix:** key the message on an unchecked batch row matching the branch name
(`feat/batch-N-*`), not on a clean tree.

## PIPE-18 · LOW · live · verified — closed rows accumulate in the "Open batches" head

Batch 154's saving held: `/next-batch-prompt` reads STATUS (6.4 KB), the build plan down to
`## Closed batches` (18.8 KB), the last session-log section (2.2 KB), its own file and
`AGENTS.md` — **38.3 KB, about 9,600 tokens**, against 529 KB before Batch 154. But the head's
"Open batches" section holds seven rows and **all seven are ticked** (115, 140, 148, 149, 150,
151, 168): 14.7 KB, 78% of the head. `strike-batch.md` ticks a row in place and nothing moves
it below the heading, so every batch the next review specifies will add to what every
cold start reads, until someone moves them by hand.

For scale: `docs/BUILD_PLAN.md` grew from 287 KB to 353 KB since `2ce6f42`, and
`session-log.md` from 271 KB to 541 KB (it now also carries the old STATUS archive). Neither
is read whole by any workflow; the risk is a tool that loads a file from the top — a 2,000-line
default read of `session-log.md` is roughly 35k tokens of history before the entry being
appended. `/batch-start` reads about 22 KB plus its row; `/group-start` about 45-50 KB before
its first batch (its own file, `09-prompts.md`, the group's section of `08-sequencing.md`,
STATUS and recent entries).

**Fix:** `strike-batch.md` moves the ticked row under `## Closed batches`; move the seven now.

## PIPE-19 · INFO · live · verified — dormant or stale machinery

- `.github/workflows/claude.yml` is an `@claude` / `auto-fix` issue workflow with
  `contents: write`, fed by issue text in a **public** repository, and it points at a
  `prod-monitor` workflow that does not exist. `gh secret list` shows no secrets and every run
  has been "skipped", so it is inert today; it is template residue from the first commit.
- 29 of the 130 commits carry no agent trailer — Batches 152, 120-122, 115, Group Z and the
  out-of-batch fixes — so which agent (or person) built what is not recorded.
- `/private/tmp/the-coupon-main-batch149` is a leftover worktree, detached at `7a1a7c7`
  (the Batch 150 close-out); `git worktree list` still lists it. Left untouched.
- `apps/api/pyproject.toml` `[project]` pins fastapi 0.111.0 and starlette 0.37.2; the gate
  runs 0.141.1 and 1.6.0 from `requirements-dev.txt`. Unused, but misleading to an agent.
- `check-closeout-safety.sh` classifies a root `vercel.json` that does not exist (the file is
  `apps/web/vercel.json`, still covered by `apps/web/*`); `check-deploy-drift.sh`'s tier-3
  probe still names Batch 51 despite its own comment to keep it current.
- `2f7d742`'s commit message and docstring credit `_future_window` to Batch 112; it came from
  the out-of-batch `d1b9ee9`.

## Checked and found nothing material

- **No weakened tests.** Across the 55 code commits: no new `skip`, `xfail`, `.only`, `.todo`
  or `.skip` in any test (the `pytestmark = skipif(no DATABASE_URL)` hits are the standard
  Postgres-module pattern, and the gate refuses any skip). Every removed or renamed test was
  read: Batch 139 (a specified default changed; reported, and a companion test added), 157
  (the owner dropped the field; the tests now pin its absence), 161 (a property deliberately
  inverted, 201 → 429, explained in the commit body), 164 (framer-motion removed), 155
  (renamed during redaction, assertions kept), 150 (first-run home replaced), 115 (a
  hand-typed round replaced by a database-derived one with a dated floor; the TTL change it
  needed was owner-approved in the row), `99b5fc9` (a dated tripwire re-measured, which is
  its purpose). Batch 140 changed an expectation from Alice to Bob in an assertion it had
  written itself, and said so.
- **Batch 131 stopped for the owner** as the run order predicted, and its session-log entry
  quotes the oracle before and after.
- **The 23 Sep round-population fix (`2f7d742`) is honest:** its own `fix/` branch, as
  `AGENTS.md` requires for a red baseline; every assertion unchanged; one test added for the
  helper's invariant.
- **Batch 166 closing with no code change is honest:** it first parked itself rather than
  sign in as the owner to measure, then closed on thirteen Lighthouse runs against a seeded
  local bundle (blocking time 915 → 265 ms median) with the remaining cost attributed to
  framework boot. Lens 04 re-takes the number.
- **Suppressions in product code are defensible:** `# type: ignore[assignment]` on a
  dependency default of `None` in `routers/auth.py` (FastAPI's pattern), and two
  `react-hooks/exhaustive-deps` disables with stated reasons; `type: ignore` in tests is noise
  (mypy checks `src` only).
- **No ratchet was raised without tests.** Every commit that raised a count also added test
  functions, and the gate's exact match fails a count raised past the real one (probe G14
  passes the guardrail, then fails the count step).
- **The 25 ticks dated 23 Sep** match 25 close-out commits dated 23 Sep. Ten batches closed
  between 01:04 and 03:41 at 12-28 minute intervals, each claiming a full 11-check gate of
  11-13 minutes; tight, but consistent with first-time passes on a quiet machine.
- **CI and the local gate agree on versions** (Node 24, pnpm 9.15.0, Python 3.12).

## Enforced by machinery, or only by prose — rebuilt

| hazard | 2026-09-13 | today |
| --- | --- | --- |
| Never weaken the gate | prose only | **script, partial**: config edits by name and falling counts are refused; the guardrail runs from the branch, five precedence files are unprotected, content changes are invisible (PIPE-10) |
| Test counts must not fall | nothing | **script**, exact ratchet — local gate only; CI does not check (PIPE-12) |
| Gate edits need owner approval | — | **script**, but the approval table is editable from the branch it approves (PIPE-10) |
| Drift before shipping | script, after the push | **script, before the push**; existing drift only reported (PIPE-14) |
| Split-half batch | — | **script refuses**; cleared by a typed flag, unrecorded (PIPE-14) |
| Migration shipment needs a written recovery plan | — | **script** (`check-migration-recovery.sh`, Batch 128) — not itself protected |
| Deployment configuration invariants | script in the gate | script in the gate and CI |
| Single replica for migrations | code | code (not re-driven here) |
| The end-to-end journey passes | — | **nothing** — outside the gate and CI (PIPE-13) |
| CI green before members get it | — | **impossible** as built: the push deploys, CI runs after, nobody reads it (PIPE-12) |
| Never force-push `main` | prose | prose — `main` has no branch protection |
| Never implement on `main` | prose | prose (the guardrail diffs against local `main`, so work committed on `main` passes it; the close-out guard would then find no diff and stop) |
| Red baseline gets its own branch | prose | prose — followed once (`fix/round-population-window-clock`) |
| Three attempts at a failing check | prose | prose |
| Report every failure | — | prose; the session-log template does not ask for CI or the guard's verdict |
| Close out only when the tree holds one batch | prose | prose (the guard classifies the diff but does not check scope) |
| Never `cd`; never pass the database URL to psql | prose | prose |
| No live provider calls in automation | prose | prose |
| Database tool scoped read-only to staging | contradicted by local config | **still contradicted** (PIPE-01) |

The 2026-09-13 pattern has moved but not closed. The *deployment* is still well mechanised,
and Batch 152 genuinely mechanised the *gate* — but by trusting the branch to run an honest
copy of it, and by stopping at the push: nothing mechanical looks at CI, the end-to-end
journey, or what happened after.

## An AI product feature?

**None.** The member-facing faults this review round is finding are ordinary engineering
problems with ordinary fixes, and the product's appeal is a private group's own banter, which
generated text would dilute. The one place a model earns its keep is this pipeline, and even
there the deterministic fixes come first: a test-ID diff (PIPE-16) and a CI conclusion
(PIPE-12) in each session-log entry tell the owner more, more reliably, than a model's summary
of the diff would. A second-model review of each batch diff for weakened tests before the push
is possible, but it would be advisory and would add minutes to every batch; not recommended
ahead of those two.

## Proposed batches

All are tooling or documentation; none carries API code or a migration, but the first five
edit protected files and so each needs its row and file list approved by the owner, as 153 and
127 were.

1. **Run the guardrail and count step from `main`'s copy; protect config by pattern; move the
   approval table out of the branch** (PIPE-10) — tooling, gate maintenance.
2. **Stamp a gate pass with the tree hash and refuse a push without it** (PIPE-11) — tooling,
   gate maintenance.
3. **Read CI after the push and stop on red; add the guardrail and count check to CI; fix the
   two flaky backend tests** (PIPE-12) — tooling plus test-only changes under `apps/api`, which
   the drift check counts as reaching the image, so a `/ship-prod` would be reported owed.
4. **Put the coupon-flow journey in the gate and CI** (PIPE-13) — tooling, gate maintenance.
5. **Refuse a web change over owed drift; record the guard's verdict and any shipment schedule
   in the session log** (PIPE-14) — tooling, gate maintenance.
6. **Close-out prints removed/renamed test IDs and turns follow-ups into rows** (PIPE-15,
   PIPE-16) — tooling and documentation.
7. **Key the stop hook on an open batch row; make `strike-batch` move closed rows** (PIPE-17,
   PIPE-18) — tooling and documentation.

PIPE-01 stays with the owner, by hand. PIPE-19 is housekeeping for whichever batch touches
those files.

## Owner decisions

1. **Should close-out wait for CI?** (PIPE-12). Options: (a) keep "Do not poll CI"; (b) wait
   for the run on the pushed SHA, record it, stop a group on red; (c) push the feature branch
   first and wait for its run before merging, so CI runs *before* members get the build.
   **Recommendation: (b)** — about 8 minutes a batch and no change to how deploys work; (c) is
   stronger but doubles CI time per batch and changes the branch policy.
2. **Should a gate change take effect only after it merges?** (PIPE-10). Running the gate from
   `main`'s copy means a gate-maintenance batch cannot prove its own new gate on its branch; it
   would run the new copy explicitly as a second, reported step. **Recommendation: yes.**
3. **Protect `main` against force-pushes** (no required checks, so pushes still deploy). An
   owner action on GitHub. **Recommendation: yes**; it costs nothing.
4. **The 22 Sep gate fixes** (PIPE-11): were they directed by the owner in a live session? If
   so, record that owner-directed gate fixes still get a row and a session-log entry. Either
   way, no rollback is needed — the changes are sound.
5. **`claude.yml`** (PIPE-19): delete it, or keep it dormant. **Recommendation: delete** — it
   is template residue with write access in a public repository.

## Doc corrections

For the lead to apply. The no-database split was re-measured for them: at `eb18bcb`, `pytest -q` with no `DATABASE_URL` is **800 passed, 550 skipped** at 1,350 tests (29 Sep).

| file | from | to |
| --- | --- | --- |
| `AGENTS.md` | "so the **520 Postgres-backed tests actually execute**" | "so the **550 Postgres-backed tests actually execute**" |
| `AGENTS.md` | "Running pytest without `DATABASE_URL` is **780 passed, 520 skipped** (measured 2026-09-24, at 1,300 tests;" | "Running pytest without `DATABASE_URL` is **800 passed, 550 skipped** (measured 2026-09-29, at 1,350 tests;" |
| `docs/agent-commands/batch-verify.md` | "It is `780 passed, 520 skipped`\n(measured 2026-09-24)," | "It is `800 passed, 550 skipped`\n(measured 2026-09-29)," |
| `docs/agent-commands/phase-closeout.md` (protected) | "`780 passed, 520 skipped` (2026-09-24)" | "`800 passed, 550 skipped` (2026-09-29)" |
| `AGENTS.md` | "including step 8's push" | "including step 9's push" |
| `AGENTS.md` | "**What that push means.** Step 8 pushes `main`" | "**What that push means.** Step 9 pushes `main`" |
| `AGENTS.md` | "`/group-start <I-Y>`" | "`/group-start <I-Z>`" |
| `docs/agent-commands/README.md` | "`/group-start <I-Y>`" | "`/group-start <I-Z>`" |
| `docs/agent-commands/phase-closeout.md` (protected — the guardrail will list it on this branch) | "For Batch 6 this also includes browser screenshots." | *(delete — a fossil from Batch 6)* |
| `docs/agent-commands/batch-verify.md` | the "Then the rest, from the shared venv" pytest command using `/Users/craigrobinson/app-starter/apps/api/.venv/bin/python -m pytest` | `/Users/craigrobinson/.cache/the-coupon/ci-local-venv/bin/python -m pytest` — `AGENTS.md` says the app-starter venv cannot collect the suite (no Pillow) |
| `STATUS.md` toolchain | "Current ratchets are 1,350 backend and 1,204 frontend tests." | *(delete — repeats the line's own "(backend 1,350, frontend 1,204)")* |
| `STATUS.md` Live table, Web | "last live-verified at `b08a47f3` (2026-09-27)" | "serves the CSS of `4121cf0`, the last web commit (checked 2026-09-28)" |
| `STATUS.md` Open batches | "Group Z's five web-only visual-pass batches are closed out; Vercel will build the final Batch 149 push from `main`." | "Group Z's five web-only visual-pass batches are closed out and live (checked 2026-09-28)." |
| `docs/BUILD_PLAN.md` | seven ticked rows (115, 140, 148, 149, 150, 151, 168) under "### Open batches" | move them under "## Closed batches", leaving the heading for the new rows from Batch 169 |

Not doc-only, so left for a batch: `ci-local.sh`'s header says it runs "the checks
`.github/workflows/ci.yml` runs" (it runs more — CI has no guardrail or ratchet); the drift
probe's "Batch 51"; `2f7d742`'s misattribution; `pyproject.toml`'s stale `[project]` pins.

## What this pass did not do

- **Did not identify who made the out-of-batch commits** (PIPE-11, and the 29 without a
  trailer). Git records only the owner's identity; the agent transcripts are not in the
  repository.
- **Did not run the coupon-flow journey** or any browser run; its rot is shown from the diff
  that repaired it.
- **Did not exercise the Supabase MCP tools** (PIPE-01) — their presence in this session is the
  evidence; calling one is exactly the hazard.
- **Did not run `check-deploy-drift.sh`** (it fetches and calls production); the replays stub
  it.
- **Did not re-verify the two CI flakes locally**; the CI logs are the evidence, and a flaky
  failure does not reproduce on demand.
- **Token counts are estimates** (bytes ÷ 4); byte counts are exact.


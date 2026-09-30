# Progress — review 2026-09-28

A cold session resumes from this file alone. Update it at every checkpoint.

Branch `chore/review-2026-09-28`, cut from `main` at `eb18bcb`. Never push, merge,
`/ship-prod` or `/batch-start` from this review.

## Setup

| step | state | evidence |
| --- | --- | --- |
| `date` checked | done | Mon 28 Sep 2026 22:40 BST |
| branch + `00-prompt.md` committed | done | `f45f128` |
| drift check | done | API `b08a47f3` at migration 026; `main` `eb18bcb` is 14 commits ahead, none reach the API image → **in sync**, exit 0 |
| full gate | **PASS, 11 checks, 11m18s** — backend 1,350 / 0 skipped, frontend 1,204 / 0 skipped, both equal to the ratchets | `notes/baseline-ci-full.txt` |
| `SKIP_PROD_BUNDLE=1` gate | **PASS, 10 checks, 10m37s** | `notes/baseline-ci-skip.txt` |
| shared harness | smoke-tested 22:47 (API health, HTTP login, bundle build, Chromium sign-in) | `notes/harness/stack.py`, `notes/harness/web.sh` |
| lens briefs | written | `notes/briefs/common.md` + one per lens |

## Interruptions

| when | what | recovery |
| --- | --- | --- |
| 28 Sep ~23:04 → 29 Sep 08:37 | usage limit stopped all four running passes (01, 02, 05, 07) minutes after launch; each had only read its brief and started notes | partial notes committed `fed7399`; stale `sec`/`corr` stacks killed; passes resumed from their transcripts |
| 29 Sep ~08:50 → 13:36 | usage limit again, ~10 minutes into six parallel passes | notes committed `a1fc4bb`. **Pacing changed: at most three passes at once**, finishing lenses rather than advancing all six; each resume re-sends a whole transcript, so fewer live passes waste less per interruption. Resumed 01, 02, 07 at 13:40 (their `sec`/`corr` stacks left running); 03, 04, 05 queued with stacks stopped |
| 29 Sep ~15:30? → 18:32 | usage limit, third time, with 03, 04, 05 running (01, 02, 07 had finished at 14:45) | notes committed `98e2284`; stacks left running; 03, 04, 05 resumed 18:35 |
| 30 Sep ~00:35 → 08:37 | usage limit, fourth time, just as 04 resumed for timings | 04 resumed 08:40 for Lighthouse + timings; lead wrote rows, 08, 09, 10 and the README meanwhile |

## Harness defect (29 Sep 18:40)

Lens 03 found `notes/harness/web.sh` built with the wrong cwd, so Tailwind emitted a 9 KB
stylesheet: every capture built with it is unstyled. Fixed at 18:50 (builds from
`apps/web`, refuses a stylesheet under 30 KB; 45.8 KB verified). Lens 02's three and lens
05's six captures are relabelled `-unstyled-` and count as text evidence only. The machine
also appears to have slept between ~18:45 and 23:13 (a ten-minute wait returned at 23:13
with load 189).

## Privacy scrub (29 Sep ~14:50)

Lens 07's `scan-test-diffs.txt` (first committed in the partial-notes commit) quoted one
full member name that Batch 155 redacted. It was replaced with "[member name redacted]"
and **this unpushed branch's history was rewritten** (`git filter-branch` over
`f45f128..HEAD`, that substitution only) so no commit on it carries the name; the
pre-scrub refs were deleted. Checked by hash, never printed. `main`'s history is
untouched, per the owner's decision.

## Lenses

| lens | state | notes dir | next step |
| --- | --- | --- | --- |
| 01 security | **done** 14:45 — 20 held / 3 partial / 1 not fixed; SEC-27..31 | `notes/01-security/` | |
| 02 correctness | **done** 14:45 — 7 held / 3 partial / 1 not fixed / 1 accepted; CORR-19..27 | `notes/02-correctness/` | |
| 03 UX / a11y | **done** 30 Sep 00:18 — 9 held / 3 partial / 1 not fixed; UX-21..33; 422 captures | `notes/03-ux/` | |
| 04 performance / ops | **done** 30 Sep 08:52 — 16 held / 1 partial / 5 not fixed; PERF-18..23, OPS-19; Lighthouse on the quiet machine | `notes/04-perf/` | |
| 05 feature gaps | **done** ~18:45 — 3 held / 1 partial / 5 not fixed; FEAT-A13..15, B10..12 | `notes/05-features/` | |
| 06 premium design | **done** 30 Sep 00:28 — 3 held / 6 partial; DES-10..23; top ten + 4 mockups; 99 captures | `notes/06-design/` | |
| 07 agent pipeline | **done** 14:45 — 4 held / 4 partial / 1 not fixed; PIPE-10..19 | `notes/07-pipeline/` | |

## Lead's own work (not delegated)

- verification of every HIGH+ finding
- `10-reconciliation.md`, `README.md`, `08-sequencing.md`, `09-prompts.md`
- BUILD_PLAN rows from Batch 169
- applying doc-only corrections on this branch

## Lead's deliverables

| file | state |
| --- | --- |
| Batches 169-203 in `docs/BUILD_PLAN.md` | done (`5e196de`) |
| `08-sequencing.md`, `09-prompts.md` | done |
| `10-reconciliation.md` | done — SEC-32 raised, DES-16 merged, no withdrawals |
| `README.md` | done, timings folded in 30 Sep 08:55 |
| doc corrections | applied, `notes/lead/doc-corrections.md` |

## Exact next step

**Review complete (30 Sep 08:55).** Awaiting the owner's review of the register and answers to
the README's decisions. Do not merge, push, `/ship-prod` or `/batch-start` anything until then.

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

## Lenses

| lens | state | notes dir | next step |
| --- | --- | --- | --- |
| 01 security | running (subagent, launched 22:57) | `notes/01-security/` | |
| 02 correctness | running (subagent, launched 22:57) | `notes/02-correctness/` | |
| 03 UX / a11y | todo | `notes/03-ux/` | |
| 04 performance / ops | todo | `notes/04-perf/` | |
| 05 feature gaps | running (subagent, launched 22:53) | `notes/05-features/` | |
| 06 premium design | todo | `notes/06-design/` | |
| 07 agent pipeline | running (subagent, launched 22:53) | `notes/07-pipeline/` | |

## Lead's own work (not delegated)

- verification of every HIGH+ finding
- `10-reconciliation.md`, `README.md`, `08-sequencing.md`, `09-prompts.md`
- BUILD_PLAN rows from Batch 169
- applying doc-only corrections on this branch

## Exact next step

Waves: 05 + 07 launched while the full gate ran. When the full gate finishes: start
the `SKIP_PROD_BUNDLE=1` gate and launch 01 + 02. When that gate finishes: launch 03 +
04 (04 defers timings until the machine is quiet). When 03's corpus is committed:
launch 06. If a subagent is lost, relaunch it pointing at its brief and its
`notes/<lens>/progress.md`.

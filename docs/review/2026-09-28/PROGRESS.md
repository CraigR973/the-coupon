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

## Lenses

| lens | state | notes dir | next step |
| --- | --- | --- | --- |
| 01 security | running (resumed 13:40) | `notes/01-security/` | |
| 02 correctness | running (resumed 13:40) | `notes/02-correctness/` | |
| 03 UX / a11y | **queued** — had started stack + bundle; restart both | `notes/03-ux/` | |
| 04 performance / ops | **queued** — next: seed_shapes.py | `notes/04-perf/` | |
| 05 feature gaps | **queued** — code-reading checkpoint committed; next: drive.py on 8150 | `notes/05-features/` | |
| 06 premium design | todo | `notes/06-design/` | |
| 07 agent pipeline | running (resumed 13:40) | `notes/07-pipeline/` | |

## Lead's own work (not delegated)

- verification of every HIGH+ finding
- `10-reconciliation.md`, `README.md`, `08-sequencing.md`, `09-prompts.md`
- BUILD_PLAN rows from Batch 169
- applying doc-only corrections on this branch

## Exact next step

Three passes running (01, 02, 07). As each finishes, resume the next queued pass
(03, then 04, then 05) by SendMessage to its agent — or, if that agent is gone,
launch a fresh one pointed at its brief and progress.md. Launch 06 after 03's corpus.
When the other passes finish, tell 04 the machine is quiet so it can take timings.
Then: verify every HIGH+, reconcile, write 08/09/10 and the README. If a subagent is lost, relaunch it pointing at its brief and its
`notes/<lens>/progress.md`.

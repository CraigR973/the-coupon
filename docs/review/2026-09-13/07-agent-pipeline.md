# 07 — Agent delivery pipeline

The application ships no LLM features, so the AI-engineering lens points at what
does use AI: **agents build this repository, and since 2026-08-27 a green batch
closes out automatically — including the push to `main` that Vercel deploys to
members.** The owner's review window is after the deploy, not before it.

Method: read-only review of the instruction files, the canonical command
workflows, the local agent configuration, the gate script, the drift and
deployment-config scripts, the CI workflow, and the test/lint configuration;
plus measurements of the documents agents are told to read, and two permitted
production GETs.

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| PIPE-01 | HIGH | live | verified | The local agent configuration contradicts the project's own database-access decision |
| PIPE-02 | MED | live | verified | The stop hook argues against automatic close-out at the moment it happens |
| PIPE-03 | MED | tooling | verified | The production-bundle smoke can test the wrong server |
| PIPE-04 | MED | tooling | verified | The gate records no test count, and several ways to weaken it are detected by nothing |
| PIPE-05 | MED | live | verified | The automatic push deploys the web half with no drift block |
| PIPE-06 | MED | doc | verified | The gate's own numbers are quoted in the present tense and are a month stale |
| PIPE-07 | MED | doc | verified | The two documents agents must read are 106k tokens, and under 2% of one is current |
| PIPE-08 | MED | privacy | verified | Two non-owner real names and their old sign-in names are in a public repository |
| PIPE-09 | LOW | tooling | verified | The local gate does not pin the package manager CI uses |

## PIPE-01 · HIGH · live · verified — the local configuration contradicts the L0 decision

The launch record states plainly that the database tooling is documentation-only
until it can be scoped read-only to staging, and that **production must never be
connected**. The Codex configuration, which is tracked, does exactly that:
staging, read-only.

The Claude Code configuration, which is gitignored and local, does not. It binds
the database tool to **a project reference that is neither staging nor
production**, with no read-only flag; the local permissions file allows the
**write-capable query tool**, auto-enables the server without a prompt, carries a
blanket allow for *any* shell command, and includes a destructive recursive
delete rule scoped to a different repository entirely.

No member is affected today — it is a local file, and this review's own
guardrails kept it unused. But any agent turn in this worktree inherits a
write-capable database tool pointed at the wrong project with no confirmation
step. That is precisely the hazard the project has written rules about.

**Fix:** mirror the Codex configuration — staging reference, read-only — or
remove the server until it is scoped; drop the blanket shell allow and the
cross-repository delete rule.

## PIPE-02 · MED · live · verified — the hook argues against the policy

Both the Claude and Codex stop hooks print, on a clean non-main branch, that the
close-out should be run "only when the user asks". The instructions say the
opposite: close-out is automatic and should run without being asked. The hook
fires at exactly the moment an agent is deciding. It exits zero, so it is
advisory rather than blocking — but it is advice that contradicts the policy.

## PIPE-03 · MED · tooling · verified — the smoke test can point at the wrong server

The gate starts a preview server on a fixed port without forcing that port, waits
a fixed five seconds, then runs a Playwright suite against a fixed URL. If that
port is already held — and the repository's own launch configuration defines a
preview server on it — the new server silently moves to a different port while
the tests hit whatever was already there. The gate would report a pass for a
bundle it never tested.

**Fix:** force the port and fail loudly if it is taken; wait for readiness rather
than sleeping.

## PIPE-04 · MED · tooling · verified — nothing notices a weakened gate

The instructions forbid reaching green by weakening the gate, and are unusually
clear about why. Nothing enforces it. The gate discards each step's output on
success, so **no test count is ever recorded** — a batch that deletes or skips
tests passes identically to one that does not, and no close-out records counts to
compare. Nothing detects a new skip marker, a silenced type error, a relaxed lint
rule, an edited expectation, or an edit to the gate script itself.

**Fix:** record the test counts in the close-out report and fail when they fall;
assert the gate script and lint/type configuration are unmodified in the batch's
own diff.

## PIPE-05 · MED · live · verified — the push deploys the web half unconditionally

Close-out pushes `main`, Vercel releases from it, and nothing checks whether the
API the new web half needs has shipped. The drift script is run and its output
printed **after** the push. There is a live instance of the consequence right
now: the Batch 113 admin Calendar page is deployed and the API route behind it
returns 404 in production, and has since 13 September.

**Fix:** run the drift check before the push and refuse to close out a batch that
adds both halves of a feature until the shipment is scheduled, or gate the web
half behind a capability check.

## PIPE-06, PIPE-07, PIPE-08, PIPE-09

**PIPE-06** — "509 passed, 151 skipped" and "88 seconds" appear in three command
documents in the present tense. Measured on this commit: **734 passed and 438
skipped** without a database, **1,172 passed and 0 skipped** with one, in 4m48s —
more than three times the quoted figure, which matters because that figure is the
argument for not skipping the database run. One document also undercounts the
full gate as ten checks; it is eleven.

**PIPE-07** — `STATUS.md` is 1,937 lines (~34.5k tokens) and **under 2% of it is
current state**: both major sections are historical narrative, one walking
backwards through completed batches. `BUILD_PLAN.md` is 4,094 lines (~71.4k
tokens) with 117 closed rows against 2 open. The session log duplicates the
per-batch narrative one-for-one. Two of the three command workflows instruct an
agent to read **all of both** — about 106k tokens — in order to find the first
unchecked row. Worse, the same document contradicts itself in ways only visible
if read to the end: a batch group described as "one batch in" and then "complete"
fifteen lines later; renamed members "not told" and then, eighteen lines on,
"two of three, correctly"; a rollback baseline "usable" and later "not usable".
None of the bold claims carries a date.

**PIPE-08** — two non-owner real names, with their old and new sign-in names,
appear in the status document, a backfill document and the build plan — all
tracked, in a repository the status document itself describes as public. Neither
prior review flagged it.

**PIPE-09** — the local gate does not pin the package manager version CI uses and
skips the browser install CI performs, so the two can diverge.

## Enforced by machinery, or only by prose

| hazard | enforced by | if ignored |
| --- | --- | --- |
| Never implement on `main` | prose only | a batch lands unbranched |
| Never weaken the gate | prose only (PIPE-04) | a green run that proves nothing |
| Red baseline gets its own branch | prose only | a fix is folded into an unrelated batch |
| Three attempts at a failing check | prose only | unbounded retry |
| Drift before shipping | script, but **after** the push (PIPE-05) | a broken web half reaches members |
| Single replica for migrations | **code** (migration guard) | — |
| Deployment configuration invariants | **script** in the gate | — |
| Never `cd` (the shell runs a local env file) | prose only | secrets echoed into a transcript |
| Never pass the database URL to psql | prose only | the password printed on the failure path |
| Database tool scoped read-only to staging | **contradicted by local config** (PIPE-01) | writes to the wrong project |
| No live provider calls in automation | prose only | the scheduler's hourly budget spent |
| Close out only when the worktree holds one batch | prose only | unrelated work deployed |

The pattern is clear: everything that protects the *deployment* is mechanised;
almost everything that protects the *process* is prose, and the process is what
an automatic push depends on.

## An AI product feature?

**None recommended.** The member-facing problems this review found are a race
condition, a scoring bug, a missing correction path, a silent result moment and a
desktop layout — every one of them better solved by ordinary engineering. The
one place a model would genuinely help is *this* pipeline: summarising what a
batch changed for the owner's after-the-fact review, which is a documentation
aid, not a product feature.

## Proposed batches

1. **Rescope the local database tooling and drop the blanket shell allow** (PIPE-01) — tooling-only, and the owner should do this by hand.
2. **Run the drift check before the push and refuse a split-half close-out** (PIPE-05) — tooling-only.
3. **Record test counts in close-out and fail when they fall; assert the gate is unmodified** (PIPE-04) — tooling-only.
4. **Force the preview port in the gate and wait for readiness** (PIPE-03) — tooling-only.
5. **Realign the stop hook with the automatic close-out policy** (PIPE-02) — tooling-only.
6. **Cut `STATUS.md` to a current-state page and split the build plan's open rows from its closed ones** (PIPE-07) — documentation, and the biggest recurring cost saving available.
7. **Redact the non-owner names** (PIPE-08) — documentation, with an owner decision on history.

## Owner decisions

- **The local database tooling** (PIPE-01): rescope to staging read-only, or
  remove it until scoped? Recommendation: rescope, matching the Codex file.
- **The non-owner names** (PIPE-08): redact the working tree only, or also
  rewrite history? Recommendation: redact now; treat a history rewrite as a
  separate decision.
- **Document restructure** (PIPE-07): worth one batch of churn to save ~106k
  tokens of cold-start reading on every future batch? Recommendation: yes.

## Proposed documentation corrections

Listed with exact replacements in `08-sequencing.md`; the stale test counts and
the gate check-count are the ones to apply first, and the hook text change should
be made by the owner rather than an agent.

# Full-application review — 2026-09-13

The third standing review of The Coupon, at commit `2ce6f42` (Batches 1-119
closed except 95 and 115), following `docs/review/2026-08-22/` and
`docs/review/2026-08-26/`. Four lenses at once: senior engineer, application
security engineer, the AI engineer responsible for this repo's agent-driven
delivery pipeline, and a product designer holding the app to the standard of a
paid consumer sports app.

## How this was produced

Parallel specialist passes, each told to spot-check its slice of the prior
registers rather than re-audit from zero, then spend its effort on the 106
commits (Batches 82-119, ~32,500 lines) that landed since the last review.
Everything marked **verified** was reproduced against something running:

- **Backend and API** — a scratch PostgreSQL at migration 025 with the seeded
  test server, driven over HTTP and in process. Two leagues with deliberately
  different windows, markets and claim scopes were played through the whole
  loop; concurrency was exercised with simultaneous submissions; calendar,
  discovery, pricing and notification behaviour were driven with counting fake
  providers. No live odds or football provider was called.
- **Frontend** — the production bundle served locally against that API, in real
  headless Chromium: axe-core 4.10.2 across 88 route/state runs in both themes,
  and a 173-image screenshot corpus at 390×844 and 1280×800.
- **Security** — a 72-route × 7-role authorisation matrix probed against the
  running instance, cross-league ID-substitution probes, a live OSV query over
  900 pinned dependencies, production response headers read over HTTPS, and a
  git-history secret scan.
- **Production** — read-only throughout: response headers, `/api/v1/health`,
  and unauthenticated probes. Nothing was written, no load was generated, no
  member session was used, and the database tooling was never invoked.

Findings rated HIGH or above were challenged before being kept, and the three
sharpest — the account takeover, the claim-race 500 and the stray round that
scores — were independently re-confirmed from source by the lead.

**This review ran over seven days rather than one**, because the account's usage
limits interrupted it five times. Two consequences the owner should know: three
passes are unfinished (listed below and in `08-sequencing.md`), and the detailed
working notes were lost to a temporary-directory cleanup, so these documents were
composed from the verified findings and evidence rather than from the raw
reports. The screenshot corpus survived and is in `screenshots/`.

## Baseline

Green, on `2ce6f42`, run twice:

| gate | result |
| --- | --- |
| `scripts/ci-local.sh` | **PASS, 11 checks, 13m12s** |
| `scripts/ci-local.sh` with `SKIP_PROD_BUNDLE=1` | **PASS, 10 checks, 6m56s** |
| pytest with PostgreSQL | **1,172 passed, 0 skipped** (4m48s) |
| pytest without a database | 734 passed, 438 skipped |
| vitest | **1,045 passed**, 61 files |
| versions | python 3.12.13 · fastapi 0.141.1 · starlette 1.6.0 · ruff 0.5.4 |

**2,217 tests pass.** Read the register in that light: this is a well-built
application, and the findings are exceptions in a codebase whose normal standard
is high.

**Deployment drift.** Production serves `b95d81dd` at migration 024. `main`
carries one further API commit — `f748117`, Batch 113, migration 025 — so **a
`/ship-prod` is owed**, and its web half is already live against an API that
404s. Every finding below is tagged `live` or `main-only` against that split.

## Register — ordered by what to act on first

| id | sev | deploy | finding | where |
| --- | --- | --- | --- | --- |
| CORR-08 | HIGH | live | The loser of a simultaneous claim gets a 500, and the app says the pick may not have been sent | 02 |
| CORR-09 | HIGH | live | A stray round left by a window change can be claimed, settles, and scores | 02 |
| SEC-15 | HIGH | live | A league admin can take over any member's account, including a site admin's | 01 |
| SEC-18 | HIGH | live | Any named member can be locked out of sign-in for a whole Saturday | 01 |
| OPS-13 | HIGH | live | No working backup: recovery point unbounded, recovery time undefined | 04 |
| OPS-11 | HIGH | live | Node 20 passed end-of-life in April and is still what CI and the web build use | 04 |
| OPS-12 | HIGH | live | Every migrating shipment leaves the API with no rollback target | 04 |
| FEAT-A10 | HIGH | live | There is no way to correct a mis-settled pick | 05 |
| PIPE-01 | HIGH | live | Local agent config binds a write-capable database tool to the wrong project | 07 |
| SEC-16 | MED | live | A removed member rejoins with the old join code; join-by-code skips approval | 01 |
| SEC-17 | MED | live | Site admins write into leagues they never joined and consume a selection | 01 |
| SEC-19 | MED | live | The web app serves no CSP and can be framed | 01 |
| SEC-20 | MED | live | The per-league display name is unvalidated — impersonation | 01 |
| CORR-10 | MED | live | A void pick lowers win rate exactly like a loss | 02 |
| CORR-14 | MED | live | A round completed by someone leaving never announces itself | 02 |
| CORR-15 | MED | live | Discovery has no budget of its own; a third window exhausts the plan | 02 |
| CORR-11 | MED | main-only | Declaring an extra week renames a round already played | 02 |
| CORR-12 | MED | main-only | The season anchor is whichever round was discovered first | 02 |
| CORR-13 | MED | main-only | Two rounds in one football week share a label | 02 |
| UX-12 | MED | live | Four more public screens render outside the app shell | 03 |
| UX-13 | MED | live | A 70% opacity drops two surfaces below AA | 03 |
| PERF-01 | MED | main-only | Home reads every round in the deployment, twice per request | 04 |
| PERF-02 | MED | live | One worker: 20 concurrent home requests take 1,254 ms each | 04 |
| PERF-03 | MED | live | An 84 KB slate is served uncompressed | 04 |
| PERF-04 | MED | live | Picks scanned per round; the round date column is unindexed | 04 |
| OPS-14 | MED | live | The silence and provider alarms reach a dashboard, not a person | 04 |
| FEAT-B07 | MED-HIGH | live | No self-service account deletion or data export | 05 |
| FEAT-A11 | MED | live | A renamed member with no push subscription can never be told | 05 |
| FEAT-B08 | MED | live | Nothing tells a member their round has been settled | 05 |
| DES-01 | high | live | 1280 is a phone layout stretched, not a desktop design | 06 |
| DES-02 | high | live | The pick screen opens with every fixture hidden | 06 |
| DES-03 | high | live | Every pick outcome arrives as the same red toast | 06 |
| PIPE-05 | MED | live | The automatic push deploys the web half with no drift block | 07 |
| PIPE-04 | MED | tooling | The gate records no test count; weakening it is detected by nothing | 07 |
| PIPE-03 | MED | tooling | The production-bundle smoke can test the wrong server | 07 |
| PIPE-02 | MED | live | The stop hook argues against automatic close-out | 07 |
| PIPE-07 | MED | doc | 106k tokens of cold-start reading, under 2% of it current | 07 |
| PIPE-08 | MED | privacy | Two non-owner real names are in a public repository | 07 |
| PIPE-06 | MED | doc | The gate's own numbers are a month stale and stated as fact | 07 |
| SEC-21 | LOW-MED | live | The cryptography pin has accreted three advisories since SEC-09 | 01 |
| DES-04..DES-09 | med | live | Toasts under the tab bar, generic skeletons, errors that look empty, no type scale | 06 |
| SEC-22..SEC-26, CORR-16..CORR-18, PERF-05, OPS-15, OPS-16, FEAT-A12, FEAT-B09, PIPE-09 | LOW/INFO | — | see the lens documents | — |

Roughly: **9 HIGH, 27 MED (including three high-impact design), and the rest LOW
or informational.** Every one was then re-checked against the source — 44 of 46
confirmed at the stated location, one refined (PERF-04) and one withdrawn
(SEC-24). That pass is `09-reconciliation.md`, and **every surviving finding now
has a batch, an owner decision, or an explicit "accepted, no action"**:
Batches 120-155.

## What is already excellent — do not churn it

- **No N+1 anywhere.** Every endpoint's statement count is identical at
  production shape and at a 50-member full-season stress shape, and identical for
  a member in one league versus three. Pick submission is a flat 12 statements.
- **Pricing is solid.** A stale price is refused with the new number, a
  1.8-versus-1.80 or fractional round trip is not falsely refused, an unavailable
  price fails cleanly, and a pick never freezes a price the provider did not
  confirm.
- **The API's security headers are exemplary** and the documentation routes are
  correctly closed; cross-league ID substitution was correctly scoped on every
  probe; the push-endpoint allowlist refused every hostile shape tried.
- **The offline pick queue works**, including the lost-race path — one POST on
  reconnect, correct messaging.
- **Every prior register item spot-checked still holds**, fourteen of them.
- **The design system is good** and both themes are considered; Batch 97's
  fill-the-viewport work on home genuinely worked.

## Owner decisions

1. **Ship migration 025 now.** Its web half has been live against a 404ing API
   since 13 September. Recommendation: ship before starting any new batch.
2. **The local database tooling** (PIPE-01) — rescope to staging read-only, or
   remove it? Recommendation: rescope by hand, today.
3. **Account deletion** (FEAT-B07) — anonymise and keep scoring history, or
   remove outright? Recommendation: anonymise.
4. **The API's worker count** (PERF-02) — the scheduler lives in the web process,
   so more workers means more schedulers. Recommendation: stay at one; move the
   scheduler out before ~10 leagues.
5. **Storage-egress attribution** (FEAT-A09) — unchanged since August and still
   the only thing blocking backups (OPS-13). Recommendation: do it next.
6. **Launch gate L5** — still open after three reviews. Recommendation: close it
   retroactively or delete it.
7. **The combined coupon and void legs** — it currently multiplies a void leg's
   price into the accumulator. Recommendation: exclude void legs.
8. **Average rank across leagues** (CORR-18) contradicts the contract.
   Recommendation: drop the field.
9. **The non-owner names** (PIPE-08) — redact the working tree, or also rewrite
   history? Recommendation: redact now, decide history separately.
10. **Restructure `STATUS.md` and the build plan** (PIPE-07)? Recommendation:
    yes — it saves ~106k tokens of reading on every future batch.

## Where this review was wrong

- **SEC-24 was withdrawn.** It read a deliberate asymmetry as a missing guard: an
  extra week is by definition a midweek date, so the Saturday rule it claimed was
  missing would forbid the feature's whole purpose.
- **PERF-04 was overstated.** Picks are indexed; the real gap is that the index is
  left-anchored on the league and cannot serve a round-only lookup, plus an
  unindexed round date column.
- An accessibility run reported a missing page title and language on the
  empty-results screen. It was a capture artefact — a dead database process under
  a live holder — and a re-run produced a clean page with zero violations. The
  finding was withdrawn.
- The first capture run produced "loading", "error" and pick-feedback screenshots
  that were actually the idle screen: the states had been named but never driven.
  The design pass caught it and the lead confirmed it by hashing the files and
  reading one image. A re-capture was started but not finished, so the corpus
  still lacks a settled-results screen, a settled combined coupon and the four
  pick-feedback states.
- The per-league display-name impersonation (SEC-20) was reported as HIGH and has
  been calibrated down to MED: points and credentials are unaffected, the admin
  still sees the true roster, and it is reversible.
- The performance pass considered the single-worker finding (PERF-02) for HIGH
  and rejected it, recording why: at today's membership, concurrency is single
  digits.

## What this review did not do

- **Three passes are unfinished**: the manual accessibility half (keyboard, focus
  rings, zoom and reflow, reduced motion, 44px targets), the web performance pass
  (bundle, Lighthouse, re-renders, query keys) and the odds-budget and scheduler
  measurements. All three are specified in `08-sequencing.md`.
- The peripheral design screens and the PWA polish pass were not judged, and the
  ranked top-ten design changes with mockups were not produced.
- No live provider verification — the real slate and pricing check remains the
  owner's. No load or authenticated testing against production.
- The documentation corrections listed in `08-sequencing.md` were **identified
  but not applied**, so this branch changes no file outside this directory.

## The documents

| file | covers |
| --- | --- |
| [01-security.md](01-security.md) | the authorisation matrix, takeover and lockout, headers, dependencies, secrets |
| [02-correctness.md](02-correctness.md) | the game rules, the claim race, the calendar, pricing, notifications |
| [03-ux-accessibility.md](03-ux-accessibility.md) | the axe sweep across 88 runs, and what the gate misses |
| [04-performance-operations.md](04-performance-operations.md) | the numbers, at two data shapes, plus deploy and recovery |
| [05-feature-gaps.md](05-feature-gaps.md) | spec-versus-built, and what a paying member expects |
| [06-premium-design.md](06-premium-design.md) | the core screens against a paid-app bar |
| [07-agent-pipeline.md](07-agent-pipeline.md) | the gate, the automatic push, and what is prose rather than machinery |
| [08-sequencing.md](08-sequencing.md) | Batches 120-155 in deployment-safe groups, and the unfinished work |
| [09-reconciliation.md](09-reconciliation.md) | every finding re-checked against the source, line by line |
| [screenshots/](screenshots/) | 173 images, indexed by `INDEX.md` |

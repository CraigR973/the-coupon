# Next session: complete the two-game contract design (Batch 219)

This bounded contracts-only handoff is retained for reference. The owner's later
[overnight prompt](two-games-per-week-overnight-prompt.md) supersedes its
stop-after-219 scope when invoked. Monday-to-Monday London billing is approved.

```text
Continue The Coupon in /Users/craigrobinson/the-coupon. Complete only the remaining contract/document work for Batch 219. Do not start storage (220) or any product implementation.

First read AGENTS.md, STATUS.md, the product contract/architecture and exact Batches 219–228 in docs/BUILD_PLAN.md, then:
- docs/two-games-per-week-plan.md
- docs/two-games-per-week-second-review.md
- docs/two-games-per-week-acceptance-examples.md
- docs/two-games-per-week-free-tier-assessment.md
- docs/two-games-per-week-live-feasibility.md
Read the latest session-log.md entry and current git status, branch, diff and HEAD. Check source/tests for every contract assumption; use an Explore subagent if investigating more than three files to learn behaviour.

Expected checkout: chore/plan-two-games-per-week at dfb39fef90dd4a171248c79117d6bdc72d63ce8d, with modified STATUS.md/BUILD_PLAN.md and untracked two-game planning/review documents. Verify rather than assume. Preserve all existing work and Git-ignored evidence. This is an authorised contract pass in that existing checkout, not a /batch-start invocation: do not require a clean-main reset, stash, worktree or planning commit to make progress. Do not commit, merge, push, deploy, tick a batch or perform close-out. Leave formal batch verification/close-out separate.

Approved rules are settled: independent group and fantasy games; group Saturday 15:00 only, one pick/member and one whole fixture/group, no odds/points, 14:30 lock, neutral void/all-void void; fantasy Saturday 12:30 through Sunday, Saturday noon lock, up to six different fixtures/member, member overlap allowed, partial entries valid, each win round(frozen odds × 10); no cross-game reservation. Existing season points remain. Next fantasy opens at the current Saturday noon lock. Every member owes £1 every calendar week regardless of play, fixtures, results or suspension; early future entry requires paid-through status including intervening weeks, using pooled FIFO credit. Preserve legacy history and unrelated leagues.

Deliver a concrete inactive API/data-identity contract in docs/two-games-per-week-api-contract.md. Specify method/path and snake_case request/response examples, league/week/game/slot addressing, statuses and refusal codes, atomic replacement/uncertain-write reconciliation, fixture/price provenance, independent openings/locks/results, week-specific fee entitlement, all actionable home states and legacy/stale-client compatibility. Identify the storage invariants needed by 220 without writing migrations or runtime code.

Incorporate every F1–F6, C1–C6 and Q1–Q9 acceptance example. Use the approved Monday 00:00–Monday 00:00 Europe/London billable interval, labelled by Saturday; define membership mapping, first applicable week and early-due materialisation before storage. Do not reopen that boundary or the £1 obligation. Cover the first live legacy coupon alongside next week's new fantasy, separately from archives and the steady-state three-game home. Preserve real rolling quota, committed transport spend across business rollback/retries/restart, and cross-caller atomic admission; existing fixed-window tests are not proof of the new meter.

Update the product contract and the single architecture map in BUILD_PLAN.md to distinguish existing legacy behaviour from the approved inactive opt-in design. Keep protected AGENTS.md unchanged and record its legacy-only product summary for separately approved alignment at integration. Keep the plan and STATUS.md consistent. Trace all acceptance cases to contract fields/responses and downstream batches; annotate unresolved activation criteria without claiming they are satisfied.

Saturday's 14 Nov noon Europe/London provider observation is already scheduled. It gates live coverage/activation, not this contract work; do not wait for it or create another automation. Existing free capacity is the baseline. Daily entitlement, supported traffic and acceptable price/result delays remain activation evidence. Keep API/payments successful-shipment parity, tested migration recovery, web push gates and exact untouched-week activation separate.

No product code, migrations, live settings/billing, provider probes, Monzo/Betfair access, jobs, picks, notifications or subscription changes in this session. Validate documentation links, examples, consistency and requirement traceability; report exactly what was checked and any unrun runtime/full-gate checks. Do not invent implementation-test evidence or mark 219 complete merely because its acceptance examples exist.

Stop after the contract pass. Report Result, Risk, You, Next in four short labelled lines, link the contract, identify any unresolved billing decision, and state whether storage (220) has a sufficiently concrete contract to begin after normal batch preconditions. Do not continue into 220 automatically.
```

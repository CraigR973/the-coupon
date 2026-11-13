# Two games per week: second review

12 Nov 2026 · source `dfb39fef90dd4a171248c79117d6bdc72d63ce8d` plus the
current uncommitted planning documents and Batches 219–228.

**Verdict: ready to begin the contracts batch (219). No new blocking design
defects were confirmed in the revised boundaries reviewed.** Storage (220)
follows those contracts; neither needs to wait for Saturday. Live activation
still requires the outstanding provider, traffic and operational evidence.

This was a focused second review, including an independent Explore reviewer,
of batch dependencies, disabled-mode behaviour, migration/payments compatibility,
durable provider admission and weekly billing/cutover. It was not a repetition
of the original full review. Source and tests were inspected; no tests, provider
queries, production operations or implementation were performed in this pass.

## Confirmed new defects, ranked

None. The source hazards examined are already represented in the revised plan:

- **Inactive behaviour:** the rollout gate precedes new workers and billing,
  with per-week format fences protecting legacy jobs and writes. This is an
  implementation requirement, not a flag that exists today.
  [Storage acceptance](/Users/craigrobinson/the-coupon/docs/BUILD_PLAN.md:1631),
  [format contract](/Users/craigrobinson/the-coupon/docs/two-games-per-week-plan.md:114).
- **Migration/payment overlap:** old payments checks migration parity at boot;
  it does not continuously stop its running reader. The revised checkpoint
  explicitly requires old-reader/new-schema compatibility and then successful
  API/payments shipment at the same head.
  [Boot verification](/Users/craigrobinson/the-coupon/apps/api/src/payments_service/boot.py:109),
  [shipment gate](/Users/craigrobinson/the-coupon/docs/two-games-per-week-plan.md:395).
- **Web release order:** Batch 227 can reach its local gate, but 228 follows
  successful API shipment and 227 close-out. A shipment scheduling acknowledgement
  cannot satisfy the stronger prerequisite. No stacked-branch exception or
  automatic activation is implied.
  [Batch sequence](/Users/craigrobinson/the-coupon/docs/BUILD_PLAN.md:1601),
  [automatic close-out](/Users/craigrobinson/the-coupon/docs/agent-commands/batch-start.md:53).
- **Durable charges:** the suspected existing transaction defect was disproved.
  The current durable limiter uses its own session and commits its counters
  before returning. Its fixed-window representation is not sufficient evidence
  for the proposed rolling provider budget; the planned transport/concurrency/
  restart tests must establish that new behaviour.
  [Separate limiter session](/Users/craigrobinson/the-coupon/apps/api/src/database.py:44),
  [commit semantics](/Users/craigrobinson/the-coupon/apps/api/src/rate_limit.py:291),
  [current fixed-window tests](/Users/craigrobinson/the-coupon/apps/api/tests/test_durable_rate_limit.py:67).

## Acceptance refinements for Batch 219

These make existing requirements concrete; they are not additional reasons to
stop before the contracts batch.

1. **Specify the billable week's exact boundary and cutover.** Write the London
   interval represented by each weekly fee and how joining, leaving, rejoining
   and early future entry map to it. Show a legacy due already recorded at
   cutover, an early future due and intervening fixture-free weeks; each must be
   charged once, with no retroactive legacy rebilling. The current ledger keys
   dues by round, not by an independently defined calendar interval, so the new
   mapping must be explicit before schema implementation. Do not reopen the
   approved £1 amount or participation-independent obligation.
   [Existing due identity](/Users/craigrobinson/the-coupon/apps/api/src/services/dues.py:170),
   [gameweek identity](/Users/craigrobinson/the-coupon/apps/api/src/models/gameweek.py:40),
   [new billing contract](/Users/craigrobinson/the-coupon/docs/two-games-per-week-plan.md:294).
2. **Include the first mixed-format live Saturday.** Before the first two-game
   playing weekend, next week's fantasy may already be open while this week's
   legacy coupon is still actionable or settling. Preserve that legacy week's
   writes, result and fee status while exposing the new fantasy target. Test
   this transition as well as the three-state steady-state home and archived
   history. The current selector deliberately prioritises a playing round; it
   cannot itself represent all actionable targets.
   [Current selection order](/Users/craigrobinson/the-coupon/apps/api/src/services/gameweek.py:439),
   [first opening/cutover](/Users/craigrobinson/the-coupon/docs/two-games-per-week-plan.md:407).
3. **Name the quota failure boundaries in the test contracts.** Include calls
   straddling clock-hour/day boundaries, a spent attempt followed by pick conflict
   or rollback, transport failure/retry and process restart. A dispatched call
   remains spent; a refused pre-dispatch reservation sends no HTTP request.
   Do not copy a fixed-window counter and claim a rolling guarantee. These
   are concrete cases under the already specified shared-budget acceptance,
   not evidence of a new defect in the existing limiter.
   [Current window reset](/Users/craigrobinson/the-coupon/apps/api/src/rate_limit.py:301),
   [attempt/retry location](/Users/craigrobinson/the-coupon/apps/api/src/services/odds_api.py:683),
   [post-fetch conflict rollback](/Users/craigrobinson/the-coupon/apps/api/src/routers/picks.py:441).

## Uncertainties and owner decisions

No new owner decision is needed to complete this review or begin 219. If the
precise billing boundary changes which week someone owes, present that narrow
choice when defining the contract; the approved £1 rule is not in question.

Resolved later on 12 Nov: the owner selected Monday 00:00–Monday 00:00
Europe/London, labelled by Saturday. The acceptance examples now include exact
join amounts; this is no longer an unanswered owner decision.

The existing activation uncertainties remain: actual opening-time fixture/price
coverage, daily account entitlement, agreed supported traffic and acceptable
price/result delays. The scheduled 14 Nov observation addresses provider
availability; it does not prove sustained service, the proposed implementation
or natural payment/notification acceptance.

The current planning checkout is preserved. Canonical `/batch-start` requires a
clean `main`; the planning changes need their normal baseline before invoking
that workflow. This is an execution precondition, not a new design defect or
reason to wait until Saturday.
[Canonical preflight](/Users/craigrobinson/the-coupon/docs/agent-commands/batch-start.md:18).

**Next: complete 219 with the three explicit acceptance examples above, then
proceed to inactive storage work. Keep shipment and activation gates intact.**

12 Nov follow-up: the owner requested these additions. The detailed
[acceptance examples](two-games-per-week-acceptance-examples.md) are now referenced
by 219 and the relevant downstream rows. Their contract implementation and
verification remain part of 219; no build row has been marked complete.

The owner's later overnight scope permits local builds/tests only. Its explicit
[run prompt](two-games-per-week-overnight-prompt.md) temporarily allows stacked
local batches through 228, while preserving the production shipment/activation
and formal close-out gates. It supersedes the ordinary local ordering described
above only when invoked, not the source findings or release requirements.

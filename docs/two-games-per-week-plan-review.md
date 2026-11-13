# Two games per week — draft review

11 Nov 2026 · Review only · `chore/plan-two-games-per-week` at `dfb39fef90dd4a171248c79117d6bdc72d63ce8d`.

The approved game rules are represented correctly. The additive football-week parent with separate group and fantasy records is a sound direction. The plan needs the changes below before becoming executable build batches.

## Evidence boundary

Reviewed AGENTS.md, STATUS.md, the product contract and relevant build rows, the draft, and current source/tests. Explore subagents covered scheduling/pricing, dues/operations and results/contracts. Tests were inspected, not run; a pure offline schedule calculation checked the DST offset. No live services or providers were contacted. Production statements below are dated repository records, not fresh verification. The existing untracked draft and checkout were preserved; this review is the only added file.

## Confirmed problems, ranked

### 1. P1 — The additive model needs a fence against legacy writes

The storage and activation gates do not explicitly prevent an old installed client from submitting a third, legacy scored pick into a two-game week. The current POST carries no game or week target, resolves the parent from league plus fixture, and writes the legacy `Pick` table. A format marker and separate tables alone do not close that route. Existing uniqueness constraints govern only the old table.

**Required change:** specify immutable week format, explicit game/week identity on new writes, and rejection of legacy writes into two-game weeks and new-game writes into legacy weeks. Define database-backed group member/week and fixture/week uniqueness; fantasy member/week/slot uniqueness with slots 1–6, plus member/week/fixture uniqueness. Test replacement collisions preserve the original pick, cross-league isolation, and stale-client writes after activation.

Sources: [draft storage/activation](/Users/craigrobinson/the-coupon/docs/two-games-per-week-plan.md:92); [request contract](/Users/craigrobinson/the-coupon/apps/api/src/routers/picks.py:196); [legacy write](/Users/craigrobinson/the-coupon/apps/api/src/routers/picks.py:418); [implicit round resolution](/Users/craigrobinson/the-coupon/apps/api/src/routers/picks.py:858); [existing constraints](/Users/craigrobinson/the-coupon/apps/api/src/models/pick.py:77).

### 2. P1 — Provider feasibility covers pick traffic, but the whole pipeline changes

Batch 5 names pick-time capacity; discovery, refresh and settlement can independently prevent the approved game:

- The repository's 23-competition test shape needs 92 requests for two windows over two dates, above the discovery cap of 90. Its current test expects only 69 requests for two windows: one farther card is omitted. That is now potentially the card promised at noon.
- The existing 11:05 refresh falls inside fantasy's final picking hour. The scheduler safety test protects the old 14:30 deadline only.
- Settlement reads each distinct pending fixture before applying any results. A set exceeding the hourly allowance can fail without saving progress; six picks and multiple leagues expand that set. Sunday picks also remain pending during Saturday sweeps.

**Required change:** put whole-pipeline capacity in Batch 1, before storage: discovery, refresh, browsing both weeks, cache warming, submissions/replacements and settlement retries. Specify supported league/member load, next-card completeness, deduplicated discovery, final-hour scheduling and bounded settlement that retains progress. Include cold/warm caches and provider refusal. The 23-competition figure is test evidence, not a current live measurement.

Sources: [discovery cap/horizon](/Users/craigrobinson/the-coupon/apps/api/src/config.py:201); [budget exhaustion](/Users/craigrobinson/the-coupon/apps/api/src/services/gameweek.py:1097); [69-request test](/Users/craigrobinson/the-coupon/apps/api/tests/test_discovery_budget.py:919); [refresh schedule](/Users/craigrobinson/the-coupon/apps/api/src/scheduler.py:1026); [old-lock test](/Users/craigrobinson/the-coupon/apps/api/tests/test_scheduler.py:400); [settlement read-before-apply](/Users/craigrobinson/the-coupon/apps/api/src/services/scoring.py:260); [one request per fixture](/Users/craigrobinson/the-coupon/apps/api/src/services/odds_api.py:516).

### 3. P1 — The home overlap is assigned to web work without its backend contract

The draft correctly requires current group, current fantasy results and next fantasy entry together. However, the API exposes one `current_round` and one `my_pick` per league; home links to a league's default round. Batch 8 cannot deliver the overlap as web-only work unless earlier API batches explicitly provide it.

Six slots also invalidate the existing offline editor's assumption that one newer intent supersedes the previous intent. Generic phone journeys will not catch losing a queued pick for another slot or reconciling an identical selection against the wrong game.

**Required change:** assign the home summary, history, fee and game/week addressing contracts to backend work before the API checkpoint. Specify game/week/slot identity in routes, cache keys, mutations and reconciliation. Gate all three home states with exact destinations; test two offline slot fills, replacement, uncertain responses, game/week switching and the noon boundary. Preserve legacy links and old-response compatibility.

Sources: [draft batch order](/Users/craigrobinson/the-coupon/docs/two-games-per-week-plan.md:96); [single-round API](/Users/craigrobinson/the-coupon/apps/api/src/routers/me.py:194); [one-row selection](/Users/craigrobinson/the-coupon/apps/api/src/routers/me.py:400); [home navigation](/Users/craigrobinson/the-coupon/apps/web/src/pages/DashboardPage.tsx:492); [single-intent editor](/Users/craigrobinson/the-coupon/apps/web/src/hooks/usePickEditor.ts:294); [supersession test](/Users/craigrobinson/the-coupon/apps/web/src/test/usePickEditor.test.tsx:368).

### 4. P1 — Shared-fee lifecycle decisions are deferred until after storage

“Handle membership changes” and “an empty or void week reverses its due” do not define two independently locked games. At Saturday 13:00 a departing member has locked fantasy and an unlocked group contribution. Existing departure logic uses one parent lock to release picks and reverse the whole due. Likewise, a void group coupon is not necessarily a void paid football week.

Payment wording also needs correction: incoming payments are pooled league credit, not earmarked to a football week. The ledger permits week IDs on dues/reversals, not payments; allocation clears oldest dues first. Existing paid-through-week logic already protects this week's paid pick from next week's unpaid due. Preserve that protection.

**Required change:** decide the fee/roster cases listed below before storage. Define one due per member/football week, FIFO credit and game-specific eligibility. Gate current group paid/next fantasy unpaid, arrears, concurrent openings/payments, join/rejoin, and one-game void without an accidental whole-week refund. Payment notices must name the actionable game/week.

Sources: [single-lock reversal](/Users/craigrobinson/the-coupon/apps/api/src/services/dues.py:418); [departure coupling](/Users/craigrobinson/the-coupon/apps/api/src/services/gameweek.py:1578); [ledger constraint](/Users/craigrobinson/the-coupon/apps/api/src/models/ledger.py:74); [paid-through calculation](/Users/craigrobinson/the-coupon/apps/api/src/services/dues.py:597); [overlapping-week test](/Users/craigrobinson/the-coupon/apps/api/tests/test_pay_to_pick.py:503); [leave/rejoin tests](/Users/craigrobinson/the-coupon/apps/api/tests/test_pay_to_pick.py:736); [payment notice selection/link](/Users/craigrobinson/the-coupon/apps/api/src/services/payment_notices.py:176).

### 5. P2 — Skipped weeks have no authoritative eligibility source

The proposed default promises the next eligible card even across a break. Current discovery looks ahead two cadence dates; an empty response creates no round. The season calendar enumerates Saturdays and declared extra dates, not which weekends genuinely have eligible football. Missing provider data therefore cannot establish a skipped week or justify reversing its due.

**Required change:** define authoritative skip evidence, bounded lookahead and explicit pending/unavailable/confirmed-empty states. Specify what happens at noon when the later eligible card is unknown. Test consecutive skipped weekends, empty responses, late recovery, season end and declared extra dates. Express seven days as London calendar days: the proposed 10,110-minute offset is correct, but DST crossings span 167 or 169 elapsed hours.

Sources: [draft skipped-week default](/Users/craigrobinson/the-coupon/docs/two-games-per-week-plan.md:176); [empty discovery behaviour](/Users/craigrobinson/the-coupon/apps/api/src/services/gameweek.py:807); [discovery horizon](/Users/craigrobinson/the-coupon/apps/api/src/services/gameweek.py:1066); [calendar construction](/Users/craigrobinson/the-coupon/apps/api/src/services/season_calendar.py:360); [empty-slate test](/Users/craigrobinson/the-coupon/apps/api/tests/test_gameweek.py:150); [London-time arithmetic](/Users/craigrobinson/the-coupon/apps/api/src/services/odds_provider.py:387).

### 6. P2 — Sunday finalisation needs a transition with no pending picks

The proposed finalisation rule is sound, but its acceptance gate misses a concrete trap. Today the last resolved pick immediately settles a round. Subsequent sweeps process pending picks, while the empty-round path skips any round containing picks. Adding only a Sunday time guard would strand a fantasy week whose submitted picks all finished on Saturday.

**Required change:** explicitly require idempotent finalisation without a new provider result. Test Saturday-only entries: points arrive Saturday, the week remains provisional, then finalises after Sunday's window with one announcement. Also test all-void entries, no entries and Sunday 23:59 kick-offs resolving on Monday. Group finalisation must remain independent.

Sources: [immediate finalisation](/Users/craigrobinson/the-coupon/apps/api/src/services/scoring.py:191); [pending-only sweep](/Users/craigrobinson/the-coupon/apps/api/src/services/scoring.py:260); [empty-round exclusion](/Users/craigrobinson/the-coupon/apps/api/src/services/scoring.py:299); [current incremental settlement test](/Users/craigrobinson/the-coupon/apps/api/tests/test_round_settled_batch_135.py:345); [empty-round test](/Users/craigrobinson/the-coupon/apps/api/tests/test_round_settled_batch_135.py:717).

### 7. P2 — Corrections and notifications need cross-game acceptance

Batch 6 lists these areas without defining their new identities. Fixture correction updates legacy picks; result notifications reduce picks to one per member; completion is unique per parent week and requires a price. Reusing those contracts could omit fantasy legs, suppress one game's event or introduce odds into group messages.

**Required change:** test one shared fixture across legacy, group and fantasy records and multiple leagues. A correction must recompute every affected outcome and weekly/season total, preserve frozen prices, audit changes and avoid duplicate messages on retry. Give events and links game/week identity; aggregate fantasy messages per member/week. Include mixed-format profiles, weekly winners/form, exports and account erasure in the lifecycle gate, not just the main standings page.

Sources: [fixture correction](/Users/craigrobinson/the-coupon/apps/api/src/routers/admin.py:1771); [correction tests](/Users/craigrobinson/the-coupon/apps/api/tests/test_pick_correction.py:444); [one-pick notification map](/Users/craigrobinson/the-coupon/apps/api/src/services/notification_triggers.py:726); [completion identity](/Users/craigrobinson/the-coupon/apps/api/src/models/gameweek_completion.py:40); [price requirement](/Users/craigrobinson/the-coupon/apps/api/src/models/gameweek_completion.py:87); [legacy-only export](/Users/craigrobinson/the-coupon/apps/api/src/services/account_erasure.py:256).

### 8. P2 — Recovery and activation gates need populated-state coverage

The draft correctly requires a tested recovery point, API-first shipment, matching API/payments image and migration, exact-head CI and explicit activation. Keep those gates. However, a clean-database upgrade does not prove preservation of populated legacy history and payment state. “Pick-free” also does not mean untouched: discovery can already create dues.

Payments refuses a revision mismatch at boot, but an already-running old reader can continue during the API-first migration. Readiness failure does not itself stop that loop.

**Required change:** rehearse a populated current-head upgrade and recovery with legacy results, dues/reversals, matched/queued payments and notification claims. Prove old-reader/new-schema compatibility during the deployment overlap. Activate before the first promised fantasy opening, or explicitly resolve already-announced schedules and dues. Specify emergency suspension after picks exist without converting populated weeks back to legacy.

Sources: [draft recovery gates](/Users/craigrobinson/the-coupon/docs/two-games-per-week-plan.md:108); [dues on discovery](/Users/craigrobinson/the-coupon/apps/api/src/services/gameweek.py:645); [payments boot refusal tests](/Users/craigrobinson/the-coupon/apps/api/tests/test_payments_service.py:64); [running reader](/Users/craigrobinson/the-coupon/apps/api/src/payments_service/app.py:85); [readiness check](/Users/craigrobinson/the-coupon/apps/api/src/payments_service/app.py:127).

## Owner decisions, separate from confirmed gaps

1. Fee and roster boundaries: decide departure/join/rejoin between noon and 14:30, one-game cancellation, both-game cancellation and no submissions. Recommend retaining the shared fee once either game has locked and reversing only an explicitly cancelled whole week; missed entries remain chargeable. Cost: members may owe a week despite leaving before the group lock.
2. Unknown future cards: approve a source for confirmed breaks and the behaviour when fixtures/prices are unpublished. A pending card cannot meet the approved pickable-from-noon promise. Recommend keeping activation blocked until evidence supports that promise; any relaxed opening or pricing rule needs a new decision. Cost: potential delay or provider expense, not quantified yet.
3. Participation and messages: define a group coupon with missing contributors or no submissions, and whether fantasy reminders target zero picks or fewer than six. Recommend distinguishing “entered” from “six slots filled”; partial entries stay valid. Cost: extra message/progress states.
4. Statistics and suspension: define leg-versus-week denominators for existing profile metrics and the post-activation stop procedure. Recommend clearly labelled leg metrics plus weekly totals/form, and suspension of new entry while preserving accepted picks and settlement. Cost: additional compatibility and recovery tests.

## Unverified live behaviour

Week-ahead fixture completeness, Sunday coverage, live prices at the actual opening, supported peak traffic and delivery/receipt remain unverified. The draft correctly requires owner-run provider evidence before storage/API work; record coverage, priced options and agreed sufficiency without treating mocks or an older Saturday card as proof. [STATUS.md's 31 Oct pricing record](/Users/craigrobinson/the-coupon/STATUS.md:22) concerns Betfair Sportsbook, despite older Bet365 wording elsewhere. Production backup status and service parity also require fresh authorised verification at shipment.

## Verdict and exact changes needed first

Not ready to turn into build batches. Preserve the approved rules and additive model, then amend the draft to:

1. Resolve the fee/roster, unknown-card, participation/statistics and suspension decisions above in Batch 1; add full-pipeline provider feasibility there.
2. Put format isolation, database invariants, explicit game/week/slot contracts and populated migration recovery into the storage/API scope.
3. Specify bounded discovery, skipped-week states, noon-safe scheduling and independent finalisation; give each its concrete acceptance cases above.
4. Move home/history/payment API contracts before the API shipment; make correction/event identities and mixed-format totals/lifecycle explicit backend gates. Keep both web batches after that checkpoint.
5. Add stale-client, offline-slot and three-state-home journeys, followed by pre-opening activation checks and the existing natural-weekend acceptance. Only then assign build numbers and bounded rows.

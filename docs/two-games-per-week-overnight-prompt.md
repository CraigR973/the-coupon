# Overnight: complete and verify the two-game build locally

12 Nov 2026 · owner selected local completion/testing, production left for review,
and Monday-to-Monday London billing. This prompt supersedes the contracts-only
handoff when invoked. It does not start a build merely by being saved.

The checkpoint/goal structure follows official OpenAI guidance on
[long-running work](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)
and [Goals](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex).
Ten substantial batches may exceed one night; a prompt cannot guarantee elapsed
time, uninterrupted computer availability or remaining usage allowance.

```text
Work in /Users/craigrobinson/the-coupon. Create a goal to complete and fully verify the local implementation of Batches 219–228, leaving production unchanged and ready for my review. Continue across batches and context compactions without waiting for me to say “continue”. Do the work; do not stop after planning, contracts or the first green batch. Mark the goal complete only when every local acceptance criterion below is met. Do not set a token budget.

I approve the existing ten-batch plan and its local schema, fee-enforcement and API changes. This is my go for the entire local run; no further go is required between these planned batches. Explain material risks briefly and proceed. Resolve routine implementation choices yourself and record them. Do not invent a new product rule, paid service or weaker acceptance criterion to finish.

FIRST READ AND VERIFY
Read AGENTS.md, STATUS.md, the product contract/architecture and exact Batches 219–228 in docs/BUILD_PLAN.md, the latest session-log.md entries, and docs/agent-commands/{batch-start,batch-verify,phase-closeout}.md. Then read docs/two-games-per-week-{plan,plan-review,second-review,acceptance-examples,feasibility,live-feasibility,free-tier-assessment}.md and this overnight prompt. Inspect current git status, diff, branch, HEAD and main. Verify current source/tests rather than treating handoffs as evidence. Use an Explore subagent when investigating more than three files, as AGENTS.md requires; independent review agents are authorised, with one batch's implementation active at a time.

Expected starting checkout: chore/plan-two-games-per-week, HEAD dfb39fef90dd4a171248c79117d6bdc72d63ce8d, modified STATUS.md/BUILD_PLAN.md and untracked two-game planning documents. Verify this; preserve all existing work and ignored private evidence. Do not reset, stash, discard, create a worktree or absorb unrelated changes. If state differs, reconcile it safely before proceeding.

LOCAL WORKFLOW EXCEPTION — EXPRESS OWNER AUTHORISATION
For this run only, use one LOCAL feature branch per batch, stacked on the preceding locally verified batch, starting from this planning checkout. Local commits of reviewed, explicitly staged in-scope files are authorised; do not use git add -A. Carry the existing planning documents into 219 rather than demanding a clean-main reset or separate planning close-out. Record each branch's parent, commit, changed files and gate evidence.

This expressly overrides clean-main-between-batches, automatic close-out and the 227/228 production-shipment prerequisite ONLY for local implementation/testing. Build and test the web against the local backend through 228. Keep main unchanged. Do not invoke /batch-start, /phase-closeout, /ship-prod, check-closeout-safety or workflows that merge, push, deploy or query live drift. Do not push any branch, open a PR, merge, deploy, migrate a remote database, change live settings, activate the format or tick canonical batch rows. Formal close-out, exact-head CI and shipment remain pending; later integration may require rebasing and revalidation. Never describe local commits as shipped or closed batches.

APPROVED RULES — DO NOT REOPEN
Each league football week has independent group and fantasy games. Group admits Saturday 15:00 London kick-offs only, one pick per member and one whole fixture across the group; no odds or points; 14:30 lock. Void legs are neutral, all-void is void, zero picks is “No coupon”, and incomplete participation is valid.

Fantasy admits Saturday 12:30 through exclusive Monday 00:00 London; Saturday noon lock; up to six independently saved picks per member on different fixtures. Members may overlap. Partial entries count. Each winning leg scores round(frozen odds × 10); losses/voids score zero. The same selection may appear in both games without cross-reservation. Existing season points remain, with future fantasy points added exactly once. Preserve legacy weeks and unrelated leagues.

Next fantasy opens at the previous Saturday noon, using London calendar arithmetic across DST. Handle confirmed breaks under the approved plan; an empty provider response does not prove a skipped week. Home must expose current group, current fantasy results and next fantasy entry together, including the first mixed-format legacy/new Saturday.

Every member owes £1 every calendar week regardless of participation, fixtures, skips, results or emergency suspension. The approved interval is Monday 00:00 inclusive to the following Monday 00:00 exclusive, Europe/London, labelled by its Saturday. Each week intersecting active membership owes once; joining is inclusive and departure exclusive. A Friday 20 Nov join owes £1 for 21 Nov, not 14 Nov. Normal billing occurs at Monday or later joining, with catch-up. Early entry requires payment through the target, including intervening weeks, and can materialise future dues early; later billing cannot duplicate them. Payments remain pooled league credit allocated FIFO. Keep already-owed fees on departure and preserve legacy dues/reversals without retroactive rebilling or charges for past non-membership. Apply every F1–F6 example.

IMPLEMENT IN THIS ORDER
219: Write docs/two-games-per-week-api-contract.md with concrete method/path, snake_case fields, identities, status/refusal codes and state examples. Map F1–F6, C1–C6 and Q1–Q9 to fields/responses and test batches. Update BUILD_PLAN.md's product contract and single architecture map, distinguishing legacy from inactive future behaviour. Keep protected AGENTS.md unchanged; list its legacy-only product summary for separately approved alignment at integration, rather than bypassing the trusted guard.
220: Add isolated parent/child storage, constraints, membership/fee provenance, durable budget/cache/cursors and a default-disabled gate. Test clean and representative populated upgrades, unchanged legacy identifiers/history/ledger, forced RLS/no public grants, old readers/writers and forward recovery. Add the required migration recovery document. Rehearse on synthetic populated scratch databases only.
221: Implement paginated shared discovery and fair, persisted chunked pricing/rechecks, both windows, bounded lookahead, skips and DST. Admit every actual HTTP attempt, including retries and legacy callers, through one durable rolling installation budget. Preserve charges/cooldown across rollback and restart; hold no provider-budget transaction/reservation lock across network I/O, while preserving safe request coalescing. Prove Q1–Q8 with counting transports and concurrent database callers.
222: Implement unconditional weekly dues, membership lifecycle, FIFO and paid-through entitlement independently of discovery, entries and outcomes. Test all F cases, races and delayed matching with fake transactions.
223: Implement explicitly addressed unpriced group reads/saves/replacements; prove uniqueness, lock, entitlement and isolation, with failed replacements preserving the old pick.
224: Implement six independent fantasy slots, per-member fixture uniqueness, fresh frozen quotes/price-moved confirmation, format-aware admission and uncertain-write reconciliation. Preserve legacy limits. Repeat real entry rollback/retry/quota cases.
225: Implement fair persisted settlement chunks, both result rules, continuous totals, corrections, game-specific events/reminders, statistics and account export/erasure. Prove Q9: partial commits survive failures/restarts without duplicated points, billing or notices.
226: Expose all actionable games, exact destinations, deadlines, week-specific payment status and legacy history. Prove C1–C6, bounded query growth and no group/locked-result pricing. Record the unperformed production checkpoint explicitly.
227: Build the group/home/archive web flow against the local API, including mobile, accessibility, concurrency, offline/uncertain replacement and inactive invisibility.
228: Build fantasy slots, simultaneous home states, continuing table and guidance. Verify two offline slot fills, replacement/reconciliation isolation, shared selections, early payment, both locks, Sunday/late results, partial/all-void/no-entry and legacy navigation.

SAFETY AND EVIDENCE
The mode is disabled by default. Until exact league/week activation, create no live new-format games, dues, notices or provider workers. Exercise enabled scenarios only in isolated fake-provider/scratch-database tests and local UI. Suspension stops new entries/openings while retaining settlement, history, corrections and billing.

Use ODDS_PROVIDER=fake and fake football/banking transports. No live odds, Betfair, Monzo, provider-account probes, production exports, token refreshes, real payments, messages, subscriptions or purchases. Local dependency installation is permitted. Do not load production credentials into local servers. The 14 Nov noon provider observation already exists: do not duplicate, alter, manually run or wait for it. Live price coverage, daily entitlement, supported traffic and acceptable delays remain unaccepted activation evidence. Candidate 90/hour and provisional 450/day budgets must be configurable and labelled assumptions; simulations must show overload/refusals rather than silently restrict membership or freeze stale quotes.

VERIFICATION AND PERSISTENCE
Run the unmodified full scripts/ci-local.sh gate for each batch milestone, using AGENTS.md's pinned toolchain and clean scratch PostgreSQL. Do not use SKIP_PROD_BUNDLE=1 for acceptance. Confirm database-backed tests execute and report actual totals/skips. Keep baseline and new assertions intact; no deleted/skipped/weakened tests, xfail, suppressions, reduced thresholds or protected gate/config/fixture edits to manufacture green. Legitimate test-count ratchet increases with added tests are permitted by the existing guard. Existing assertion replacement requiring trusted-main approval is a blocker, not permission to bypass it.

Fix the batch's own failures and rerun the whole gate, respecting the three-attempt rule for the same failing check. Reused-database resets use only disposable local schemas and do not consume those attempts. Pre-existing main failures or genuinely unapproved oracle changes stop the affected dependency chain: preserve evidence and continue only useful independent work. Never claim a red milestone complete or build dependent work on unaccepted contracts. Record every failure and fix.

Keep a durable journal under ignored .local/overnight-two-games/ with the current milestone, branch/parent/commit, remaining criteria, decisions and gate logs. Resume from it after compaction rather than restarting or ending with a handoff. Give brief Result/Risk/You/Next progress updates. Do not stop for routine choices or a late hour; continue while meaningful authorised work remains.

Before finishing, obtain an independent review against the approved rules, source, tests and F/C/Q cases; fix confirmed in-scope defects and rerun affected milestones plus the final full gate. Verify a real seeded local browser → API → scratch database flow; document how I can run/view it. Update STATUS.md and docs/two-games-per-week-overnight-report.md honestly before final verification. Record the verified tree and whether evidence predates any commit/document changes; never imply an old stamp verifies a changed tree.

DONE means all ten batches' LOCAL implementation and acceptance checks pass on the final tree, documentation/architecture match, and the morning report identifies per-batch branches/commits, gate evidence, design decisions, failures/fixes and remaining release gates. Canonical rows stay unchecked. No production recovery point, API/payments shipment parity, exact-head CI, live provider service, notification receipt or natural-payment acceptance is claimed. Production still needs a tested recovery point before migration, successful API/payments same-head shipment before web release, and separate exact-week activation approval.

If a genuine blocker or system limit prevents completion, leave an exact resumable checkpoint and clearly label unfinished batches; never report “everything complete” with missing criteria. Final chat: four short labelled lines Result, Risk, You, Next, with the report link, count of locally verified batches and exact next review/release step.
```

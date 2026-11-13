# Two games per week: contract acceptance examples

12 Nov 2026 · required by the second review and Batch 219.

These examples refine the approved rules. They are requirements for the contract
and subsequent tests, not implemented behaviour or a completed API specification.
Batch 219 remains incomplete. The owner approved the Monday billing boundary on
12 Nov. No production budget or live coverage exception is selected here.

## 1. Weekly billing boundary and cutover

The owner selected Monday 00:00 inclusive to the following Monday 00:00
exclusive, Europe/London, labelled by the Saturday within that interval. The
week labelled 21 Nov therefore runs from 16 Nov 00:00 to 23 Nov 00:00. A Friday
20 Nov join owes £1 for 21 Nov, not another £1 for the preceding week.

Each calendar week intersecting an active membership interval owes £1 once;
joining is inclusive and departure is exclusive. Normal billing is due at the
Monday boundary, or on joining later in the week, with idempotent catch-up.
Early entry can materialise the target and intervening obligations before their
ordinary billing instant; those already-owed fees survive departure. The contract
must specify stable identities, parent mapping and the first applicable week at
rollout. Calendar arithmetic must survive DST; a week is not always 168 hours.

Use W0=14 Nov, W1=21 Nov, W2=28 Nov and W3=5 Dec as Saturday labels. Assume
continuous membership unless stated. F1 is an already-activated league test;
F3 separately tests the legacy cutover, without rebilling historical weeks.

| Case | Required result |
| --- | --- |
| F1: Membership begins immediately before, exactly at, or immediately after Monday 23 Nov 00:00; the member then remains active. | Joining at 22 Nov 23:59:59.999 owes W1 £1 and, at Monday, W2 £1: £2 across two weeks. Joining exactly at 23 Nov 00:00 or one millisecond later owes W2 £1 and no W1 due. A 20 Nov join owes W1 £1. No duplicate due or charge for a wholly pre-membership week. |
| F2: Leave before the boundary, after a due was already owed; rejoin during the same week. | Preserve that obligation and history, release only unlocked claims, and charge the same week once. Crossing the boundary after departure creates no new obligation solely from the clock; explicitly reconcile any future due already owed from early entry. |
| F3: W0 is legacy and already has its £1 due/payment; W1 is the first two-game week. | Preserve W0's ledger and format. Create W1's one £1 obligation under the new contract without rebilling W0 or creating a second due when normal billing later catches up. No live new-format obligation is created before activation. |
| F4: W0 is paid; W1 fantasy opens while W0's group remains open, and W1 is unpaid. | W0's paid group contribution is allowed; W1 fantasy is refused until paid through W1. Paying W1 does not create a second fee for its other game or slots. |
| F5: W0 is paid, W1 and W2 have no fixtures, and W3 fantasy opens early. | W1, W2 and W3 each cost £1. The outstanding amount through W3 is £3. A further £1 clears W1 first, leaving £2 owed; a further £2 clears the remainder. Payments stay pooled credit, never earmarked to W3. |
| F6: Discovery, scheduled billing, join/rejoin catch-up and an early pick race to record the same week. | Exactly one net £1 due for that membership/week; no missing intervening fee, duplicate charge or lost payment allocation. No pick or outcome creates an extra charge or automatic refund. |

The contract must distinguish the football-week label from the billing instant;
W1 fantasy can open at Saturday 14 Nov noon before its Monday 16 Nov billing
period begins. Entry still requires W1 paid early; Monday cannot charge it
again. Opening a future game does not redefine the calendar interval. Legacy
dues/reversals are preserved, including any different historical policy.

## 2. First mixed-format live Saturday

W0 is a published legacy week. W1 is the first untouched two-game week. W1's
fantasy opens at W0's Saturday noon; W0's legacy pick window still locks at its
announced time. The rollout does not reclassify W0 as an unpriced group game.

| Case | Required result |
| --- | --- |
| C1: Before W1's noon opening. | W0 retains its legacy representation, lock, picks, frozen odds, fee status and points rules. W1 follows its own stored opening; no early entry or fabricated current fantasy game is offered. |
| C2: At noon and until W0's lock. | Home exposes both the actionable W0 legacy coupon and W1 fantasy entry, with exact week/game destinations and independent fee states. Neither hides the other. W1's group follows its own opening/lock contract. |
| C3: A member changes W0's legacy pick while filling a W1 fantasy slot. | Each request changes only its explicit target. Legacy claim rules still apply in W0; fantasy overlap rules apply in W1. The rollout flag does not disable valid writes to W0. |
| C4: An old client writes to W0, then attempts a legacy write to W1. | The valid W0 request remains supported; the W1 request receives the documented unsupported-format response without writing a pick, fee or provider request. |
| C5: W0 is in play while W1 accepts fantasy picks. | The single-current-round ordering cannot suppress W1. W0's points stay provisional/final according to its legacy rules; W1 has no result or points merely because picks were accepted. |
| C6: W0 settles, then W1 becomes the current playing week. | W0 keeps its original history. Home transitions to current group, current fantasy results and next fantasy entry as applicable; season totals count legacy points plus settled fantasy points once. New group picks add no points. |

Cover this transition separately from both archived legacy history and the
three-game steady-state Saturday. Batch 226 defines the read API; 227–228 verify
the web flow. The first activation still requires an untouched target week and
explicit owner approval.

## 3. Rolling quota and failure ownership

Test with configurable caps H per rolling hour and D per rolling 24 hours. The
candidate model uses H=90 and D=450; D remains an assumption pending account
evidence. These values are not changed production settings. Every caller and
every actual retry shares the same installation budget.

| Case | Required result |
| --- | --- |
| Q1: H−2 attempts occur just before a clock-hour boundary; three more arrive just afterwards. | At most two further attempts dispatch until older charges leave the rolling hour. A clock change does not mint H new requests. |
| Q2: D−1 attempts fall within the rolling day before midnight; two arrive after midnight. | At most one dispatches until older charges leave the rolling 24 hours. A calendar-day reset cannot bypass D. |
| Q3: A dispatched quote is followed by a price-moved refusal, uniqueness conflict or request rollback. | The HTTP attempt remains durably charged. The business transaction can roll back without refunding provider spend or losing the previous slot. |
| Q4: A logical quote fetch receives two transport/5xx failures and succeeds on its third dispatch. | Three attempts are charged, each admitted before dispatch, rather than one cache-refill charge. Retries stop when quota or the provider's refusal policy requires it. |
| Q5: Admission is refused before dispatch. | No HTTP request is emitted and no pick is partially written. Record refusal separately from dispatched-attempt spend; abuse limits may still count the user action. |
| Q6: The process dies after committed reservation/dispatch and before the pick response. | Restart preserves the charge and existing work. An uncertain dispatch is treated conservatively; restarting or retrying never creates free quota or duplicate writes. |
| Q7: Two leagues, a background worker and a retry compete for one remaining allowance. | Atomic admission dispatches at most one additional request. Short independent budget transactions do not hold the global reservation lock across network I/O. |
| Q8: A shared positive quote is still within the pick-time freshness limit. | Overlapping member requests can reuse it without another HTTP charge; stale or missing data takes the bounded fresh path. No stale positive quote is frozen merely to fit quota. |
| Q9: Settlement commits a completed chunk, then a later chunk fails or the process restarts. | Completed results and charges survive. Pending/error work resumes fairly without repeating points, notices or billing; the failure does not reset or roll back the global allowance. |

Source evidence: the current durable limiter commits on an independent session;
it is not defective merely because it receives an `AsyncSession`. Its fixed-window
storage/tests do not prove the new rolling transport budget. Preserve legacy
limiter tests and add coverage for the new meter rather than weakening assertions.

## Delivery and verification

Batch 219 must map each example to concrete API fields/responses, week/fee identity
and the implementation batch that will test it. Billing cases feed 220/222,
mixed-format cases feed 224/226–228, and budget cases feed 220–221/224–225.
These examples are not a substitute for the full batch gate or live acceptance.

Saturday's provider observation runs alongside contract/build work. Coverage,
account entitlement and accepted traffic/latency still gate activation; migration
recovery, API/payments parity and successful shipment retain their own gates.

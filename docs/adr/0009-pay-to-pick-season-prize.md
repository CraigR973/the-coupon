# ADR 0009 — Pay to pick: a per-round entry fee towards a season prize

Status: **accepted**, 2026-10-13, and amended the same day for weekly dues; not yet
implemented (Batches 205-208). It amends
the product contract's last bullet in `docs/BUILD_PLAN.md` and the README's
"does not place bets or handle money".

## Context

On 2026-10-12 the owner asked that members pay into a Monzo pot before they can
make a pick. The owner's answers, on 12 and 13 Oct:

| Question | Answer |
| --- | --- |
| What the money is for | A prize pot |
| How often members pay | Every round |
| Which leagues | 2-1 Hibs only (slug `2-1-hibs`, the one live league) |
| What the prize is | One prize for the full season |
| The fee | £1 a week, owed by every member every week, whether they play or not |
| A missed week | Rolls over: skip week 3 and week 4 costs £2 to play |
| A mid-season joiner | Owes from the round open when they join; earlier weeks are never owed |
| Where the Monzo token lives | A separate payments service (option B below) |
| Legal basis | A friends' league, not run as a business, under the four rules below |

The members already pay, outside the app, through one shared Monzo payment link
titled "Weekly Coupon". Nothing in the app knows who has paid.

The product contract ends "the product is for points and fun and never places a
wager", and the README says the game "does not place bets or handle money".
ADR 0004 turned down a betslip export so that the product carried no
gambling obligations. This feature is a deliberate, bounded exception. The app
still never places a bet, and it never holds or moves money. It records
payments made to the organiser and refuses an unpaid pick.

## Decision

1. **A per-league entry fee, off by default.** A league may carry
   `entry_fee_pence` and the Monzo payment link its members pay through. Only a
   site admin can set either; league admins cannot, so nobody can swap in their
   own link. Every league without a fee behaves exactly as today, and no league
   is named in code.
2. **Weekly dues; a member must be paid up to pick.**
   - Every member owes one fee for every round of the season, whether they pick
     or not. A due is recorded when a round opens, against each active member.
   - A member who joins while a round is open owes that round. Rounds before they
     joined are never owed.
   - Payments clear the oldest dues first, and anything beyond them is credit
     carried forward.
   - The API refuses a pick unless the member's balance, including the current
     round's due, is zero or more. So a missed week rolls over: skip week 3 and
     week 4 costs £2.
   - Picking, changing a pick or re-picking after a postponed fixture costs
     nothing extra.
   - The refusal has its own code and is never a 401, because a 401 signs the
     member out.
3. **One prize for the season.** The season's pot is the dues for that season's
   rounds that have been paid. The season boundary is the one the standings use
   (`season_bounds`, Batch 96), so the pot and the table always agree. The
   season's standings winner takes the pot, and a tie splits it. Payout happens
   outside the app, which only shows the pot.
4. **Corrections are reversals.**
   - A voided round cancels its dues for everyone.
   - Leaving the league before a round locks cancels that round's due.
   - Arrears and credit stay on a member's balance into the next season. Whether
     a member in arrears can win is the owner's call at payout.
   - Credit is repaid outside the app and recorded as a cash-out entry.
   - Every ledger entry is permanent. A correction is a reversing entry, recorded
     with who made it.
5. **A separate payments service holds the Monzo token.** It is a second Railway
   service built from this repository, and the only process with Monzo
   credentials. It uses its own Monzo OAuth client. It only reads from Monzo:
   no pot moves, no feed items.
6. **Matching on the payer, not a reference.**
   - Only payments that carry the league's payment-link id count, so other
     money from the same friends, such as a dinner split, is ignored.
   - A Monzo-app payer is recognised by their Monzo user id.
   - A card payer gets a new anonymous id on every payment, so they are
     recognised by their name, normalised.
   - A first-time payer goes to an admin queue. The owner assigns them once,
     and the mapping is remembered.
7. **Four rules keep the league outside licensing:**
   - 100% of fees go to the prize, with nothing deducted.
   - The league stays private: the app refuses public joining while a fee is on.
   - The league is never promoted.
   - Members are adults: each confirms once that they are 18 or over before the
     payment link is shown.

## Evidence

All checked between 12 and 13 Oct 2026.

**Monzo, live.** A read-only pull of the last 89 days of the owner's account,
through the `~/monzo-spike` token, recorded counts and data shapes only:

- 25 payments came through one link (`unipaylink_…`) into one Monzo collection
  pot (`collectionpot_…`). Monzo files them into that pot itself, and no pot
  transfer is involved.
- 14 were paid in the Monzo app:
  - scheme `p2p_payment`, with `p2p_initiator: collection-pot`;
  - 5 payers, each with a stable `user_…` id, paying 4, 4, 3, 2 and 1 times;
  - none carried a message.
- 11 were paid by card:
  - scheme `topup`, with `link_type: collection_pot`;
  - a fresh `anonuser_…` id every time;
  - 6 distinct names, paying 3, 2, 2, 2, 1 and 1 times;
  - 6 carried a message.
- The collection pot is not returned by `/pots`, so the app keeps its own totals
  from transactions.
- The token refreshed unattended after five weeks idle. An earlier six-week gap
  behaved the same on 2026-09-07.

**Monzo, documented.**

- Webhooks are unsigned and retried five times. A webhook is therefore only a
  nudge: the service re-reads the transaction from the API, and also reads
  everything since its last pull every few minutes.
- Only one live token can exist per OAuth client per user, and a new one
  invalidates the old. The service therefore cannot share the spike's client.
- The developer API may connect only to the developer's own account or "a
  small set of users you explicitly allow". It cannot pay third parties.
- Monzo's current account terms (v2.11, 18 Aug 2026) forbid business use and
  say nothing against a friends' prize pot. Under its payment button the link
  page shows "This is a personal collection, not a raffle or prize draw".

**Legal.**

- A paid league whose prize depends on the number of entrants is pool betting.
  Run as a business, it can need a pool-betting operating licence.
- Section 296(3) of the Gambling Act 2005 exempts betting "otherwise than in the
  course of a business". The Gambling Commission's notice of 17 Jul 2017 says
  leagues not run as a business, or run privately, are not caught.
- "Course of a business" is judged case by case. Promotion counts against a
  league, including posts in private groups.
- This is a managed judgement, not a ruling. If the owner wants it confirmed,
  the question to put to the Commission or a solicitor is: does a private,
  unadvertised, approval-only league of about a dozen friends, paying a weekly
  fee that is returned in full as a season prize, act "otherwise than in the
  course of a business" under section 296(3)?

**The Coupon.**

- `submit_pick` is the only member write path. A re-pick updates the same row.
- The gate fits between the market check and the odds budget charge, so a
  refused pick spends no odds requests.
- A fixture postponed before the lock deletes the pick and asks the member to
  pick again (`_drop_voided_fixtures`).
- `release_unlocked_picks` (leave, remove, delete, erase) and
  `void_non_scoring_round` are where refunds hang.
- League settings are typed columns, audited as `league_updated`.
- No money columns, inbound webhooks or signature checks exist today.

## Options considered for the token

| | A. Inside the API | B. Separate payments service (chosen) | C. Manual only |
| --- | --- | --- | --- |
| If the API is broken into | 90 days of the owner's banking readable, and fake cards can be posted into his Monzo app | Nothing from Monzo: the token's key lives only in the payments service | Nothing |
| The owner's transaction stream | Reaches the member-facing app | Reaches only the payments service, which keeps link payments and drops the rest | n/a |
| Cost | Least | About one batch more (Batch 207) | Least, but about a dozen manual entries a week |

B was chosen because the member-facing API is the most exposed part of the
system: public sign-up, PIN logins and most of the code. Manual entry is built
anyway, as the fallback for cash payments and Monzo outages.

## Consequences

- Batch 205: the API ledger and gate. Batch 206: the screens. Batch 207: a
  second Railway service, which is owner-approved gate maintenance. Batch 208:
  the payments service.
- A card payer is matched by name, which can attribute a payment to the wrong
  member. The admin queue and reversing entries are the remedy.
- If Monzo is unavailable, members can still pay, and the owner records cash or
  assigns queued payments by hand.
- **Launch steps (owner):**
  1. Rotate the spike's client secret, which has been pending since 2026-09-07.
  2. Create the service's own confidential OAuth client and seal its variables
     on Railway.
  3. Ship both services.
  4. Connect: approve in the browser and in the Monzo app.
  5. Confirm that 2-1 Hibs is private.
  6. Set its fee and payment link.
  7. Record each member's opening balance (what they've paid towards the weeks
     since dues start) as an adjustment.
  8. Pay £1 through the link and see it arrive as credit.
  9. Tell the members the four rules.

## Sources

- Gambling Act 2005: [section 296](https://www.legislation.gov.uk/ukpga/2005/19/section/296),
  [Schedule 15 Part 2](https://www.legislation.gov.uk/ukpga/2005/19/schedule/15/part/2),
  [section 46](https://www.legislation.gov.uk/ukpga/2005/19/section/46)
- Gambling Commission, [fantasy football organisers warned](https://www.gamblingcommission.gov.uk/news/article/gambling-commission-warns-fantasy-football-organisers-to-not-get-caught-out)
  (17 Jul 2017)
- [Monzo developer documentation](https://docs.monzo.com/);
  [Monzo current account terms](https://monzo.com/legal/terms-and-conditions/)

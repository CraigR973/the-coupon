# 02 — Correctness: does it work as expected

Judged against the product contract and the acceptance text of the batches that
landed since the last review, not against intuition.

Method: two leagues were seeded with deliberately different configurations —
League 1 on the defaults (Saturday 15:00 window, lock 30 minutes before,
`MATCH_ODDS`, `selection` scope) and League 2 on a Friday 19:00-22:00 window with
a 60-minute lock, both markets, a competition subset and `fixture` scope — with
twelve members, two of them on non-London profile timezones and two playing in
both leagues. The pair was driven through open → pick → claim conflict → lock →
settle → standings → combined coupon → season archive over HTTP and, for the
member-facing half, in headless Chromium at 390×844. Lock and settle were
advanced by calling the scheduler's own job functions against the scratch
database. Calendar, discovery, pricing and notification behaviour was exercised
in process against scratch PostgreSQL at migration 025 with counting fake
providers; no live provider was called.

## Prior register — spot-checked

| id | holds? | evidence |
| --- | --- | --- |
| CORR-01 malformed UUID | yes | 422 and 404 across three routes, never 500 |
| CORR-02 lock re-checked after the odds fetch | yes | still ordered correctly |
| CORR-03 / OPS-10 pick budget | yes | per-member and per-league buckets both charged |
| CORR-05 DST-hour window | yes | every transition-hour window still refused with 422 |
| CORR-07 mute gate | yes | no trigger skips it |
| FEAT-B01 offline pick queue | yes | one POST on reconnect; win and lost-race messaging both correct |
| Batch 112 core retirement rule | yes | a zero-pick round off-cadence retires; another league's round on the same date is untouched |
| Batch 114 pricing | yes | see "checked and found nothing material" |
| Batch 89 `PICKS_BUSY` | yes | refuses with nothing frozen |

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| CORR-08 | HIGH | live | verified | The loser of a simultaneous claim gets a 500, and the app tells them the pick may not have been sent |
| CORR-09 | HIGH | live | verified | A stray round left by a window change can be claimed, settles, and scores |
| CORR-10 | MED | live | verified | A void pick lowers win rate exactly like a loss |
| CORR-11 | MED | main-only | verified | Declaring an extra week silently renames a round that has already been played |
| CORR-12 | MED | main-only | verified | The season anchor is the first round discovered, not the first canonical Saturday played |
| CORR-13 | MED | main-only | verified | Two rounds in one football week both take the same bare label |
| CORR-14 | MED | live | verified | A round completed by someone leaving never announces itself, and later misattributes the final picker |
| CORR-15 | MED | live | plausible | Daily discovery has no budget of its own; a third window would exhaust the hourly plan |
| CORR-16 | LOW | main-only | verified | The season-rollover week is split across two season calendars |
| CORR-17 | LOW | live | verified | The reminder job skips the repeated hour when the clocks go back |
| CORR-18 | LOW | live | verified | The cross-league summary aggregates rank, which the contract says it does not |

## CORR-08 · HIGH · live · verified — the claim-race loser is told the app failed

Ten or more simultaneous submissions for one selection produce exactly one
winner — the uniqueness invariant holds, and no double claim was ever created.
But several of the losers receive **HTTP 500** instead of the 409 the code
intends. The handler catches the integrity error and rolls back correctly, then
builds the conflict message from the league object the rollback has just
expired; reloading it needs a database round trip in a context that cannot do
one, which raises inside the exception handler.

The 500 carries no CORS header, so in the browser it is not an HTTP error at all
— it surfaces as a network failure, and the offline queue reports "we didn't hear
back" and then "didn't land — ready to send again", when in truth the selection
is gone. Fixture scope behaves the same way.

**Member impact:** on a Saturday, the member who loses a simultaneous grab is
told the app broke rather than that someone beat them to it.

**Disproof attempted:** no guard or refresh exists between the rollback and the
message; no test drives two concurrent commits into this path; the code is
identical at the deployed commit. Rated HIGH rather than CRITICAL because no
pick is lost or duplicated.

**Fix:** read the value the message needs before the commit, or refresh the
object before using it, and return the 409.

## CORR-09 · HIGH · live · verified — a stray round scores

Change a league's window from Saturday to Friday mid-week and the current week's
Saturday round is stranded. Retirement is bounded by the furthest date in the new
cadence, so a round one day past it survives the next couple of discovery runs.
Meanwhile it is still listed to members, and the pick path checks only status and
time — so anyone browsing the rounds list can claim it. **Once it holds a pick it
can never be retired**, because retirement refuses rounds with picks.

Settlement has no per-week guard and standings sum every settled round in the
season, so both that week's Friday round *and* the stray Saturday round settle
and both count. In the reproduction one member finished on 100 points from five
scoring rounds against another's 80 from four, on otherwise identical play.

The stray round is invisible on home and the coupon until after its own lock, so
it is reachable but not obvious.

**Member impact:** a member who happens to open the stray round banks a scoring
round nobody else in the league had, and the season table is wrong.

**Disproof attempted:** confirmed there is no settle guard, no per-week collapse
in standings and no cadence check on the pick path, and that the round is
enumerable by an ordinary member; the control case without a pick *is* retired at
the next discovery run, so the window is roughly two days — narrow, but the
resulting pick is permanent. Live at the deployed commit.

**Fix:** extend the retirement bound through the end of the football week
(the following Tuesday) so a same-week stray is retired before it can be picked,
and refuse to settle more than one round per league per football week.

## CORR-10 · MED · live · verified — a void pick counts against win rate

Win rate is wins divided by picks *played*, and played includes void. The
contract says a void pick "scores nothing rather than counting as a loss". A
member whose only pick was voided shows 0%; a member with one win and one void
shows 50% where it should be 100%. Points themselves are correct — only the
derived percentage is wrong.

The scoring module already excludes void from the *odds* denominator and explains
why; the reasoning was never carried to the rate.

**Fix:** divide by the priced count. Note the existing oracle test encodes the
current behaviour, so the fix must change that test — which, under this repo's
gate rules, is a change to report rather than to take silently.

## CORR-11 · MED · main-only · verified — declaring an extra week renames a played round

`declare_extra_week` validates only the season and that the date is not a
canonical Saturday. It has no past-date or settled check, unlike the anchor move
(which refuses once locked) and the extra-week withdrawal (which refuses once
picked). Declaring a Wednesday in a past week renamed an already settled, already
picked Saturday round from "5" to "5b"; declaring a date before the anchor
renamed week 1.

**Member impact:** an admin action silently renames a round members already
played and were scored under, with no preview and no undo.

**Fix:** refuse past dates and settled weeks, mirroring the anchor rule.

## CORR-12 · MED · main-only · verified — the anchor is whichever round arrived first

The season anchor is taken from the first round discovery happens to write, with
no comparison across leagues, and is never recomputed. With a Friday league
discovered before a Saturday league, the stored anchor was a week later than the
first canonical Saturday actually played, so week 1 split into "1" and "1b" and
the rest of the season sat a week short. The batch's own text says the anchor
should be the first canonical Saturday on which *any* league holds a round.

**Fix:** anchor from the earliest canonical Saturday across all leagues' first
rounds of the season.

## CORR-13 · MED · main-only · verified — two rounds in one week share a label

When CORR-09's two rounds coexist, both render the plain week number. The
`b`/`c` suffix is derived only for *declared* extra weeks, never for an
accidental second round, so the member sees two entries both called "Gameweek 8".
The fix travels with CORR-09.

## CORR-14 · MED · live · verified — a round completed by attrition says nothing

A round can become complete because the last member who had not picked *leaves*,
is removed, or is deactivated. None of those paths fires the completion
notification or writes the completion row. Nothing announces the coupon is ready.
Worse, a later unrelated pick change on that round then triggers the completion
event and names that member as the one who completed it.

**Member impact:** the league is never told the coupon is complete, and when it
finally is, it credits the wrong person.

**Fix:** re-evaluate completion on membership change, and attribute the event to
the transition rather than to whoever wrote last.

## CORR-15 · MED · live · plausible — discovery has no budget of its own

Daily discovery costs roughly windows × dates × competitions. The competition
list is narrowed, but not per window, and the horizon is two weeks, so a third
distinct window across the deployment puts the run at about 120 requests against
a 100/hour plan — it would take a 429 partway and starve the later window. Batch
119 fixed exactly this class of failure; the cliff has moved from two windows to
three. Not triggerable today (one window in production). The silence alarms would
surface it after the fact; nothing prevents it.

**Fix:** give the run its own budget and make it degrade window by window rather
than by exhausting the plan.

## CORR-16, CORR-17, CORR-18 · LOW

**CORR-16** — the football week that straddles the season boundary is split
across two season calendars with independent anchors, so a Wednesday in the old
season and the Saturday four days later take unrelated numbers and cannot share a
declared extra week. No league plays that boundary yet. It is also a case where
the season bounds and the football-week calendar disagree, which Batch 96's row
says cannot happen — worth recording rather than fixing now.

**CORR-17** — the reminder job runs on a wall-clock cron in London, so when the
clocks go back it skips the repeated hour; a round locking between roughly 03:45
and 04:30 that morning gets no reminder. The hourly lock sweep has no such gap,
so locking and settlement are unaffected.

**CORR-18** — the cross-league summary exposes an average rank across leagues,
while the contract says points and win rate aggregate but rank does not. Harmless
in practice, but it is a live contradiction of the contract: either drop the
field or amend the contract.

## Checked and found nothing material

The full lifecycle across both league configurations: claim conflicts refused
correctly in both scopes, submissions after lock refused, wins scoring
`round(odds × 10)`, losses zero, voids scoring nothing, standings summing the
season, the combined coupon multiplying the frozen prices, the archive excluding
a settled round from the live table while keeping it viewable, and recent form
not spanning the boundary. Last-two-slots concurrency produced exactly one
completion event. A member on a New York profile saw kick-off and deadline times
correctly on a London-window league. The no-league first run is correct.

**Pricing (Batch 114) is solid.** A stale price is refused with the new number; a
1.8-versus-1.80 round trip and a fractional display preference are *not* falsely
refused (the client sends the raw decimal, fractional is display only); a price
that becomes unavailable produces a clean refusal, never a 500; and a pick never
freezes a price the provider did not confirm. `PICKS_BUSY` refuses with nothing
frozen. The stale largest-round figure from Batch 115 lives only in a test and
does not affect runtime behaviour.

Match states (scheduled, live, finished, postponed, cancelled) map correctly from
both the canned and the recorded provider payloads; team-season ordering and the
"next playable match" marker are right; home's per-league summary is correct
across open, picked, locked, between-rounds and no-rounds leagues, including one
whose latest round had just been retired. The calendar's lock instants and the
discovery and lock jobs are correct across both 2026 and 2027 clock changes.

A sweep of everything that changed since the last review for naive local-time
arithmetic, hardcoded Saturday or 15:00 assumptions and unfiltered "latest round"
lookups found only comments, no live defects.

## Proposed batches

1. **The loser of a simultaneous claim gets a 500 and is told their pick may not have been sent** (CORR-08) — API-carrying.
2. **A stray round left by a window change can be picked, settles and scores** (CORR-09, CORR-13) — API-carrying.
3. **A void pick counts against win rate** (CORR-10) — API-carrying, changes an oracle test.
4. **Declaring an extra week renames a round that has already been played** (CORR-11) — API-carrying.
5. **The season anchor is whichever round was discovered first** (CORR-12) — API-carrying.
6. **A round completed by someone leaving never announces itself** (CORR-14) — API-carrying.
7. **Daily discovery has no budget of its own** (CORR-15) — API-carrying.
8. **The reminder job skips the repeated hour when the clocks go back** (CORR-17) — API-carrying, low priority.

## Owner decisions

- **Does the combined coupon include a void leg's price?** It currently
  multiplies every frozen price, void included — which the contract's wording
  literally supports, though real accumulators settle a void leg at 1.0.
  Recommendation: exclude void legs.
- **Average rank across leagues** (CORR-18): drop the field or amend the
  contract. Recommendation: drop it.
- **CORR-16 season-rollover split**: accept as a known limitation for now.
  Recommendation: accept.

## What this pass did not do

No live provider calls. DST behaviour was exercised at the service and job level
rather than by moving the machine clock. The postponement hand-back was not
re-exercised under a clock change.

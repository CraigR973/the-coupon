# 05 — Feature gaps

Two questions, kept brief and grounded in the actual routers and components:
what the product's own spec promises that is not closed (Part A), and what a
paying member would expect that is missing (Part B).

## Prior dispositions — confirmed

| id | state today |
| --- | --- |
| FEAT-A01 launch gate L5 | **still open** — the launch plan's L5 items are all unticked and the launch log has no L5 entry; the owner's 2026-08-27 "close it retroactively" was never actioned |
| FEAT-A02 backups | **still open** — Batch 95 unchecked, no off-box destination added; see OPS-13 for what that costs today |
| FEAT-A09 storage egress | **still unattributed** — no investigation recorded anywhere; it is what blocks Batch 95 |
| FEAT-A08 renamed members | sharpened → FEAT-A11 |
| FEAT-A03, A04, A05, A07 | closed as shipped |
| FEAT-B01 offline picks | holds — verified working, including the lost-race path |
| FEAT-B03 season boundary | holds — the leaderboard has a season selector |
| FEAT-B04 league audit log | holds |
| FEAT-B06 share a settled result | holds |
| FEAT-B05 search/filter history | sharpened → FEAT-B09 |
| Batch 115 largest-round figure | genuinely an open owner decision, correctly recorded; the stale number is test-only |
| Batch 116 "a league named The Coupon" | accepted known gap — not re-reported |
| Batch 113 calendar backfill | **two-layer**: the API half has not shipped, and even once it does the backfill is a separate explicit owner action |

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| FEAT-A10 | HIGH | live | plausible | There is no way to correct a mis-settled pick |
| FEAT-B07 | MED-HIGH | live | plausible | No self-service account deletion or data export |
| FEAT-A11 | MED | live | plausible | A renamed member with no push subscription can never be told |
| FEAT-B08 | MED | live | plausible | Nothing tells a member their round has been settled |
| FEAT-A12 | LOW | live | plausible | The signup kill switch closes the API but not the screen |
| FEAT-B09 | LOW | live | plausible | The results history has no season filter, though the leaderboard does |

## FEAT-A10 · HIGH · live — no way to correct a mis-settled pick

The manual settle endpoint refuses to re-settle anything already settled, and its
own docstring says a genuine override "means correcting the pick, which is a
different act and is not this endpoint". No correction route exists anywhere in
the admin surface. This is not hypothetical: a member's pick has already needed
correcting once, and it was done with a bespoke one-off script explicitly scoped
as "not a general import path".

**Member impact:** if a result is settled wrongly — a provider error, a
postponement caught late — the points stand, and the only remedy is an engineer
writing a script against production.

**Fix:** an audited, site-admin-only correction that re-settles one pick and
recomputes the affected standings, writing an audit row.

## FEAT-B07 · MED-HIGH · live — no account deletion, no data export

The only deletion is a site-admin soft delete that deliberately keeps the display
name reserved, so a member's real name stays on historic leaderboards
permanently. There is no self-service deletion and no export of any kind. Since
Batch 74 the login identifier is a real name, and the product is UK-facing.

**Member impact:** a member who wants to leave cannot remove themselves or get
their data, and their name remains visible after they have gone.

**Fix:** self-service deletion that anonymises the display name while preserving
scoring history, plus a simple data export. Worth an owner decision on whether
deletion anonymises or removes.

## FEAT-A11 · MED · live — the rename notice can never arrive

The rename notice is push-only, with no in-app fallback anywhere. One of the
three renamed members has no push subscription, so no marker is ever written and
every boot retries. That member cannot be told through any channel until they
enable push — not "eventually", but structurally never. `STATUS.md` records this
as a timing note ("watch for that third marker"); it is a design gap.

**Fix:** an in-app notice on next sign-in as the fallback channel.

## FEAT-B08 · MED · live — the result moment is silent

Five notification triggers exist: a member joined, provider trouble, the pick
reminder, picks opening, and a pick being made (including the all-picked
hand-off). **None fires when a round settles.** The weekly loop's payoff — the
moment points are awarded — is the one moment the product never tells anyone
about. A member has to open the app and go looking.

**Fix:** a settlement push per league, gated by the existing per-league mute.

## FEAT-A12 and FEAT-B09 · LOW

**FEAT-A12** — the public-signup kill switch is checked only in the API. The
register screen has no knowledge of it, so with signups closed a visitor still
gets the full form and only learns after filling in a name and a PIN twice.

**FEAT-B09** — the leaderboard got a season selector with Batch 96; the results
and history list did not, so it still runs unbounded across season boundaries.

## Not a gap

Live in-play status of a member's own pick (built, refreshed on a schedule);
pick reminders before lock (built and scheduled); pick history and personal
stats (built, both per-league and career); leaving a league (built, handles the
last-admin case); multi-league switching (built and used consistently). League
chat is absent and is out of scope for this product.

## Proposed batches

1. **A mis-settled pick can only be corrected by writing a script against production** (FEAT-A10) — API-carrying.
2. **A member cannot delete their account or get their data** (FEAT-B07) — API-carrying + web; needs the owner decision below.
3. **Nothing tells a member their round has been settled** (FEAT-B08) — API-carrying.
4. **A renamed member with no push subscription can never be told** (FEAT-A11) — API-carrying + web.
5. **The register screen ignores the signup kill switch** (FEAT-A12) — web-only, needs the config route to be readable unauthenticated.
6. **The results history has no season filter** (FEAT-B09) — web-only.

## Owner decisions

- **Account deletion**: anonymise and keep scoring history, or remove outright?
  Recommendation: anonymise — it preserves league history while meeting the
  expectation.
- **Launch gate L5**: still open after three reviews. Recommendation: close it
  retroactively from the Saturdays that have already played, as decided in
  August, or delete the gate if it is no longer meaningful.
- **Storage-egress attribution** (FEAT-A09): unchanged and still blocking
  backups. Recommendation: do it next; it is the cheapest unblock in this list.

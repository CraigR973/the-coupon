# 03 — UI/UX and accessibility (axe sweep, objective findings)

Method: the real app on `main` at commit `3795854`, served by the Vite dev server
against a local `tests.e2e_server` API on data seeded and then played through a
full pick → lock → settle cycle (Alice picked Arsenal @1.90 and won 19 pts, Bob
picked Forfar Athletic @2.40 and won 24 pts, Carol picked a losing selection),
so every screen that only shows something once a round has settled — the home
result panel, the standings form line, the combined coupon, the Season tab —
has real content rather than an empty state. axe-core 4.10.2 was injected into
the live page and run at 390×844 for both themes, plus the unauthenticated
`/login` and `/register` (signup) screens, which the prior 2026-08-22 review
did not cover (registration was not yet public — it shipped in Batch 63,
after that review's commit `308bc16`). 10 screens × 2 themes = 20 axe runs, 20
full-page screenshots.

This document is the objective half only — every axe violation captured, and
what has changed since `308bc16` (Batches 54–81) that bears on accessibility.
The subjective "does this look premium" pass on the screenshots is being done
separately by a human; UX-05 (home screen is one card and a lot of empty
space) and UX-06 (pick-screen block order) from the prior review are
deliberately not re-litigated here, beyond noting that UX-05 is now stale —
see below.

## Axe violations captured

| id | impact | screens affected | node count | note |
| --- | --- | --- | --- | --- |
| `landmark-one-main` | moderate | light-login, dark-login, light-signup, dark-signup | 1 each (4 total) | `<html>` has no `<main>` landmark |
| `page-has-heading-one` | moderate | light-login, dark-login, light-signup, dark-signup | 1 each (4 total) | no level-one heading on the page |
| `region` | moderate | light-login, dark-login (5 each) · light-signup, dark-signup (6 each) | 22 total | page content outside any landmark |
| `color-contrast` | serious | light-standings only | 2 | avatar initials fail AA |

Zero violations of any kind on: home, pick-screen, combined-coupon, results,
settings, football-stats, career-profile (both themes), and standings in dark
mode. No `link-name`, `button-name`, `label`, or `aria-*` violations anywhere,
matching the prior review's finding.

**Totals by impact across all 20 runs: 1 serious, 3 moderate (distinct rule
IDs), 0 critical, 0 minor.**

### The moderate cluster is one root cause, confined to two screens
`LoginPage` and `RegisterPage` render outside `ProtectedRoute`/`Layout` (see
`apps/web/src/App.tsx:143-150`), so they don't get the `<main>` landmark
`Layout.tsx:14` provides or the `<h1>` that `PageHeader.tsx:65` provides on
every authenticated screen — "Sign in" and "Create account" are `<h2>` inside
a `Card`, not a page heading. This is genuinely new territory: the prior
review's screen list was all-authenticated, and `/register` didn't exist as a
public route until Batch 63. Fix is mechanical — wrap the content in a
`<main>` and promote the card title to an `<h1>` (or add a visually-hidden
one) on both pages.

### The serious one: avatar initials fail AA in light mode, and it's a
pre-existing token-reuse bug, not a Batch 78-81 regression
`li[data-testid="standing-1"]` (Bob) and `standing-3` (Carol) — both hashed
by `tintFor()` in `apps/web/src/components/ui/avatar.tsx:33-38` onto the
"bronze" palette slot — render `#A65E2A` text on a `color-mix(bronze 15%,
transparent)` background over `--surface`, measuring **4.05:1** against a
4.5:1 requirement.

This is the same fill-vs-text collision `index.css` already solved once:
every brand colour in this file has a paired `-ink` variant specifically
because "the fills... sit under `--on-primary`... [while] as text [they sit]
on `--surface`... [and] no colour satisfies both" (`index.css:126-131`). A
`--bronze-ink: #A45D29` already exists for exactly this reason — but
`avatar.tsx`'s `PALETTE` array uses `text-[var(--bronze)]` (the raw medal-fill
colour), not `text-[var(--bronze-ink)]`. I checked whether swapping to the
existing ink token would clear it: it doesn't quite — `#A45D29` on the same
mixed background measures **4.14:1**, still short of 4.5. So this needs an
actual colour fix (a darker bronze-ink specifically for the 15%-tint
background, or a stronger tint), not just a variable swap. The same
`PALETTE` array uses raw `--primary`, `--accent`, `--metal-dark`, `--gold`,
and `--metal` for text too — none of those happened to be exercised by this
3-member seed (Alice landed on a passing slot), so this is worth auditing as
a class of bug rather than assuming bronze is the only failing entry. Only
2 of 6 palette slots were exercised in dark mode's rendering either, so dark
mode passing here is not strong evidence dark mode is clean — it's evidence
this seed didn't hit a failing slot in dark mode.

This long predates Batch 78-81 — `avatar.tsx` and its `PALETTE` are unchanged
since Batch 6 (`72945c0`), so it was present at the prior review too but
wasn't caught, presumably because that review's 3-member seed didn't happen
to hash onto the bronze slot on the screen it checked.

## What Batches 78-81 changed, and what I checked for each

**Batch 78 — `PickRow`, roster/coupon unification, "Season" tab rename.**
`PickRow.tsx` is now drawn by both `MemberRoster` and `CombinedAccaView`.
No axe violations on pick-screen, combined-coupon, or results/Season in
either theme. Screenshots confirm the "Season" tab (`light-results.png`,
`dark-results.png`) and the settled pick-screen state
(`light-pick-screen.png`) render as described in the commit message — a
locked banner, "YOUR PICK" panel, and grouped-by-competition fixtures behind
disclosures.

**Batch 79 — home card result panel.** `LastResultPanel` in
`DashboardPage.tsx:237-301` is the biggest a11y-relevant addition in this
window and it's carefully built: the rank-movement arrow is `aria-hidden`
with an `sr-only` "places gained/lost" spoken alternative
(`DashboardPage.tsx:256-261`), so movement never relies on colour alone, the
same rule the prior review found the live scoreline already followed. Axe
found nothing on home in either theme, and `light-home.png` /
`dark-home.png` show the panel — rank arrow, "Your pick won · 19 pts", "2 of
2 picks landed", form pips — rendering cleanly.

**Batch 80 — `PickFormLine`, form on the leaderboard.** This is a new
component (`apps/web/src/components/PickFormLine.tsx`) and it's the one
place the serious violation above surfaces, though the violation is on the
*avatar* next to it, not on `PickFormLine` itself. `PickFormLine` is
well-built for accessibility: `role="img"` with a full spoken sentence
(`aria-label="...last rounds, oldest first: won 19 points, ..."`), the
per-round pips are `aria-hidden` since the label already carries the
information, and colour is never the sole carrier — each pip keeps its
letter (W/L/V). It correctly avoids the football-club three-letter form
convention on purpose (there's no draw state for a coupon pick, and the
component's own comment explains why borrowing one would erase the
`picks_played`/`picks_priced` distinction).

**Batch 81 — form carried to the home card.** Same `PickFormLine`, reused
in `LastResultPanel` per Batch 79's screen rather than nested inside the
standings link — the commit message notes this was deliberate specifically
*because* `PickFormLine`'s `role="img"` label would otherwise get appended to
the link's accessible name ("Standings, #1 of 4, 38 pts, last rounds oldest
first: won 35 points, void"). Confirmed this reasoning holds: axe found no
`link-name` issues on home, and the form line sits outside the "STANDINGS"
link in `light-home.png`.

## UX-05 is now stale
The prior review's UX-05 ("the home screen is one card and ~900px of
nothing... no next kick-off, no recent result, no what-other-members-did")
is largely what Batch 79-81 built: `light-home.png` now shows a result
panel with the pick outcome, points, rank movement, and a five-round form
line under the league card. There is still a large empty area below the tab
bar at 390×844 once a league has settled its round (visible in
`light-home.png`/`dark-home.png`), so the "mostly empty" part of UX-05 isn't
fully resolved, but the "nothing else competes for the space" complaint no
longer holds for a member with a settled round. Leaving the final call to
the human visual pass as instructed, but flagging that the premise changed.

## Verified good (carried over from the prior review, still true)
* Focus rings, `PinInput`, and form-pip visibility: unchanged and not
  re-tested pixel-by-pixel, but nothing in Batches 54-81 touches them and no
  new violation appeared.
* Pinch-zoom (UX-01, critical) is fixed: `apps/web/index.html:36` no longer
  sets `maximum-scale`/`user-scalable=no` (Batch 55, `f92ba17`). Confirmed
  no `meta-viewport` violation on any of the 20 runs — this was axe's only
  critical finding last time and it's gone.
* Every interactive element still carries an accessible name — no
  `link-name`/`button-name`/`label` violations on any of the 20 runs.
* Rank movement and the acca leg status both encode state in more than
  colour (arrow+word, badge text), consistent with the prior review's
  finding about the live scoreline.

## Screenshot and axe artifact index
All files under `/tmp/coupon-review/`.

Screenshots (`screenshots/`, 20 files, `{theme}-{screen}.png`):
`light-login`, `dark-login`, `light-signup`, `dark-signup`, `light-home`,
`dark-home`, `light-pick-screen`, `dark-pick-screen`, `light-combined-coupon`,
`dark-combined-coupon`, `light-results`, `dark-results`, `light-standings`,
`dark-standings`, `light-settings`, `dark-settings`, `light-football-stats`,
`dark-football-stats`, `light-career-profile`, `dark-career-profile`.

Axe JSON (`axe/`, 20 files, same naming, `.json`): full violation objects
(id, impact, description, help URL, tags, every failing node's target
selector, HTML, and failure summary), plus `passesCount`/`incompleteCount`
for context.

## Environment notes — not product findings
* Seed state: rather than the stock `/__e2e/seed` empty-round state, I ran
  the full pick → lock → settle flow (see `/tmp/coupon-review/seed_flow.py`)
  so the Batch 79-81 result/form surfaces would have real content to audit
  instead of rendering nothing. `MemberRoster`'s "n to go" and the pick
  screen's pre-lock state (both already covered by the prior review) were
  not re-captured this pass as a result — only the post-settlement states
  are in this screenshot set.
* Local dev server over plain HTTP reproduced none of the prior review's
  service-worker artifact; not investigated further since it was already
  logged as environment noise, not a product issue.

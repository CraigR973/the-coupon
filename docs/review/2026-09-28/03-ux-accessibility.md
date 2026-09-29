# 03 — UI/UX and accessibility (objective checks only)

_In progress — findings are written in as they are verified. Working notes, scripts and raw
output: `notes/03-ux/` (`progress.md` says where the pass is)._

## Method

The production bundle, built by `notes/03-ux/build_web.py`, served on `127.0.0.1:4330` against
the review harness's seeded scratch API on `127.0.0.1:8130` (`tests.e2e_server:app`, FakeBetfair,
`ODDS_PROVIDER=fake`, scheduler off, migration 026). Driven in real headless Chromium (Playwright
1.60, Node 24), `deviceScaleFactor: 1`, service workers blocked, theme and session written to
`localStorage` before first paint. axe-core 4.10.2 injected into the live page.

**The shared harness's bundle was unstyled.** `notes/harness/web.sh` runs `vite build <root>`
from outside `apps/web`, and `tailwind.config.ts` resolves its `content` globs against the process
working directory, so Tailwind emitted no utilities: the stylesheet was 9.1 KB against the gate's
45.8 KB and every page rendered as unstyled text. The first five captures of this pass were taken
against it and discarded. `build_web.py` runs the same build with `cwd=apps/web` (from Python, no
shell `cd`) and refuses to serve a stylesheet under 30 KB; every result below is from that build
(CSS 45,794 bytes, identical to the gate's). Lenses 02 and 05 have already marked their captures
from the first build as unstyled in `screenshots/INDEX.md`.

States were seeded in process with the app's own models (`notes/03-ux/seed_states.py`): Alice is
site admin and league admin of `the-coupon`, Bob a member (and admin of a second league,
`sunday-club`, with fixture scope, match odds only and a **locked** round), Carol a member, Dave
in no league, Erin a pending join request, an unclaimed invite, and a **2025/26 archive** season
(two settled rounds with won, lost and void picks). Loading states hold the page's main request
open; error states fulfil it with a 500; forced-empty states fulfil it with `[]`; offline drops the
network after load. The settled current round comes from the e2e server's own lock and settle
endpoints after real picks.

At 390 the viewport is 390×844 with a desktop user agent — the layout an installed PWA gets. The
mobile install gate is triggered by user agent, not width, so it is measured separately with an
Android UA.

## Prior findings

_Being re-driven._

## Register

_Findings are added as they are verified; the table is completed at the end._

## UX-21 · MED · live · verified — a lost pick is dimmed below AA on the player profile

`PlayerProfilePage.tsx:160` puts `opacity-60` on a lost pick's whole row, the same
opacity-over-tuned-token pattern as UX-13 and UX-18. axe-core `color-contrast`, **4 of 4 runs**
(390 and 1280, both themes) on `/leagues/the-coupon/players/:id`, re-run and reproduced:
the fixture line and odds at **2.24-2.39:1 light, 2.61-2.76:1 dark**, and the red "Lost" badge
at **2.80:1 light, 2.68:1 dark** (4.5:1 required, 12px text). Rendered-pixel measurement agrees:
fixture line #9fa5ae on #fbfcfd = 2.41:1 light, #545c6b on #0f131a = 2.77:1 dark; badge
2.81:1 / 2.69:1. Evidence: `notes/03-ux/axe/open/player-profile--happy--*.json`,
`notes/03-ux/probe-contrast.txt`, `screenshots/player-profile--happy--390--light.png`.

**Member impact:** the one row that explains why a member's points did not move — which pick
lost, at what price — is the hardest text on their profile to read.

**Fix:** drop the row opacity and let the "Lost" badge carry the state (it already says so);
if de-emphasis is wanted, use `text-text-muted` on the secondary line, which is tuned to AA.
Fix together with UX-18 and the coupon's lost leg (`PickRow.tsx:238`, same pattern).

## UX-22 · MED · live · verified — the phone install gate is outside any landmark, and the sign-in form behind it is still live

On a phone browser that has not installed the app, `InstallPromptController` covers every
route with `<BrowserOnboarding />` in a `fixed inset-0` overlay — **without** the `landmark`
prop that Batch 137 gave the `/welcome` and `/join` renderings of the same component. Driven
with an Android user agent at 390×844 over `/login`:

- axe `region`: **6 nodes**, both themes, re-run and reproduced (`install-gate--mobile-browser--390--*.json`).
- The overlay has no role, no `aria-modal`, and the page behind is neither `aria-hidden` nor
  `inert`: the document exposes **two `<h1>`s**, "One Saturday pick. One shared coupon." and
  "Sign in".
- **Every Tab stop is on the covered sign-in form**: 25 presses cycled name → PIN ×4 → Sign in
  → Forgot PIN? → Create account, each one hidden under the overlay (`probe-gate.txt`). A
  sighted keyboard user sees no focus at all (SC 2.4.11 Focus Not Obscured, 2.4.7), and a screen
  reader reads install instructions and an invisible sign-in form interleaved.

**Member impact:** the first screen every new phone visitor sees cannot be navigated by landmark,
and keyboard or switch users are sent into a form they cannot see.

**Fix:** render the gate with `landmark` (one `<main>`, one `<h1>`), and make the page behind it
`inert` (or render the gate *instead of* the route rather than over it).

## UX-23 · LOW · live · verified — the two profile pages lose their heading while loading or failed

`/leagues/:slug/players/:id` and `/profile` render their only `<h1>` from the loaded data, so the
loading and error states have none: axe `page-has-heading-one` on **16 of 16** loading/error runs
of those two routes (both widths, both themes), re-run and reproduced. Every other route keeps its
`PageHeader` through loading and error.

**Fix:** render the page title from the route (as the other pages do) and fill the name in when it
arrives.

## UX-24 · LOW (design: med) · live · verified — "Football Stats" wraps in the tab bar and crushes its icon

At 390×844 — the width of every current iPhone — the bottom tab bar's "Football Stats" label wraps
to two lines inside its 78px item and the icon is squeezed to **20×8px** (every other tab's icon is
20×20), so it renders as a dot (`screenshots/team-season--happy--390--dark.png`, measured on `/`
and `/football`). The same label also wraps in the desktop header at 200% zoom (UX-27).

**Fix:** a shorter label ("Stats" or "Football") or `whitespace-nowrap` + `shrink-0` on the icon.

## UX-25 · MED · live · verified — six more screens still show a failure as empty, blank or loading

Batch 149 gave six screens a distinct error state with a retry (home, standings, results,
football, career profile, team season) and those hold: a 500 on their main request renders
`query-error-state` with "Try again" in all 24 runs. Every other screen tested does not. Each was
driven by fulfilling its main request with a 500 and comparing against the loading and true-empty
captures (hash-compared; identical hashes listed in `notes/03-ux/duplicates.txt`):

| screen | what a 500 looks like | evidence |
| --- | --- | --- |
| **the coupon** (current round) | "No coupon this week yet" with the raw text "Internal Server Error", no retry | `current-round--error--*` |
| My Leagues | header and buttons, then nothing — no list, no empty copy, no error | `my-leagues--error--*` |
| League members (admin) | the heading "Members" and nothing else | `league-members--error--*` |
| League activity (admin) | pixel-identical to its true empty state | `league-audit-log--error--*` = `--happy--*` |
| Site admin: players | "No players match that." | `admin-players--error--*` |
| Site admin: dashboard | skeletons that never resolve — pixel-identical to loading | `admin-dashboard--error--*` = `--loading--*` |

The player profile shows "Player not found … or their profile couldn't be loaded" (no retry),
which is honest but conflates the two.

**Member impact:** if the round request fails on a Saturday morning, the pick screen tells the
member there is no coupon this week — the one message most likely to make them close the app
without picking.

**Fix:** `QueryErrorState` on the round page first (its `isError` branch already exists and
renders `EmptyState`), then My Leagues and the admin screens. Web-only.

## UX-26 · LOW (design: med) · live · verified — the tab bar's "current" marker sits two tabs to the right

Batch 164 replaced the framer-motion indicator with one measured `<span>` (`TabBar.tsx:173`,
`absolute top-0`, no `left`). Inside a `flex justify-around` list an absolutely positioned child
with no inset takes its static position from `justify-content` — centred — so its base offset is
**156px** and the measured `translateX` is added to that. Measured at 390 on five routes: the
marker is over Football Stats on Home, over Leagues on the coupon, over More on Football Stats,
and **off-screen** on Leagues (x=390) and More (x=468). `aria-current` and the label colour are
correct, so the state is still conveyed; the marker is simply wrong on every phone screen.
Evidence: `notes/03-ux/probe-indicator.txt`; visible in `current-round--error--390--dark.png`.

**Fix:** `left-0` on the indicator (and check `ui/tabs.tsx`, which uses the same hook).

## UX-27 · LOW · live · verified — at 200% zoom the header overflows and pushes the account menu off-screen

Batch 168 kept the desktop header at 200% zoom (1280×800 at 200% = 640×400 CSS px). It is kept,
and the content area is now 343 of 400px (86%; the 2026-09-13 measure was 142px of chrome). But at exactly the `sm`
breakpoint the header — logo, five links, theme toggle, account menu — does not fit: the page
scrolls sideways by **79px** on home, the coupon and standings, "Football Stats" wraps, and the
account menu (profile, sign out) sits beyond the right edge (`notes/03-ux/probe-zoom.txt`,
`notes/03-ux/zoom200-_.png`). `/login` does not overflow.

**Fix:** let the header nav collapse to icons or move Settings into the account menu between `sm`
and `md`; assert `scrollWidth <= clientWidth` at 640 in the reflow spec.

## UX-28 · MED · live · verified — keyboard focus lands behind the tab bar and the sticky header

The page has no `scroll-padding`, so when Tab moves focus to a control below the fold the browser
scrolls it just into the viewport — behind the fixed 60px tab bar on a phone — and Shift+Tab
scrolls it just under the sticky 57px header. Hit-testing five points on every focused control
(`notes/03-ux/obscured.mjs`, `obscured.txt`):

- **390, the coupon, Tab forward: the selection buttons themselves are fully hidden** ("Arsenal
  1.90 win 19 pts", "Draw 3.75 win 38 pts") — the rendered-pixel focus capture of those stops shows
  only the tab bar (`notes/03-ux/focus/round-390-light-stop12.png`).
- Shift+Tab, fully hidden under the header: the four PIN digits on Settings (1280), the round's
  "Current round / Season" sub-nav (1280), "Back" and three form fields on league settings (both
  widths).

This is WCAG 2.2 SC 2.4.11 Focus Not Obscured (Minimum), level AA — new since the 2026-09-13
register, which measured ring contrast but not position.

**Member impact:** a keyboard user choosing a pick on a phone cannot see which selection they are
about to claim.

**Fix:** `html { scroll-padding-top: <header height>; scroll-padding-bottom:
calc(var(--tabbar-height) + var(--safe-bottom)) }` below `sm`, header height only above it; add
an obscured-focus assertion to the prod-bundle smoke.

## UX-29 · LOW · live · verified — two places still clip the new focus ring

Batch 158's ring is a 2px gap plus a 3px `--primary-ink` box-shadow. Box-shadows are clipped by
an `overflow` ancestor, and two patterns clip it:

- **Fully:** the "How scoring works" toggle (`OddsGuide.tsx:61`) is a full-width button inside an
  `overflow-hidden` card, so its ring is never drawn — **zero changed pixels** on focus in all four
  runs (both themes, both widths). A keyboard user gets no focus indication at all on it.
- **Partly:** chips inside horizontal scroll strips (the round's "Current round / Season" sub-nav,
  the league switcher, the season strip, the site-admin sub-nav) lose the top and bottom of the
  ring to `overflow-x: auto`; the sides remain at 4.72:1 light / 7.62:1 dark, so focus is visible
  but the ring is broken (23 stops across 3 pages; the remaining 4 failing stops are the obscured selections of UX-28).

**Fix:** an inset ring (`inset 0 0 0 2px`) or `outline` with a negative offset for controls that
sit flush inside clipping containers; `py-1` on the scroll strips so the ring has room.

## UX-30 · MED · live · verified — Escape on every other dialog still drops focus onto the page body

Batch 167 fixed UX-16 for the bottom-nav "More" sheet only, and that fix holds (Escape returns
focus to "More", `:focus-visible`). Every other dialog in the app is opened from state rather than
from a Radix `Dialog.Trigger`, and has the exact defect UX-16 described. Driven from the keyboard
at 1280 (`notes/03-ux/keyboard2.mjs`, `keyboard2.txt`): open, confirm focus moved inside, Tab 12×
(containment held in all five — 0 escapes), Escape:

| dialog | focus after Escape | next Tab lands on |
| --- | --- | --- |
| Leave league (League actions menu, league admin) | `<body>` | "Home", top of the page |
| Delete league (League actions menu) | `<body>` | "Home" |
| Leave (standings, member) | `<body>` | "Home" |
| Leave league (members page) | `<body>` | "Home" |
| Delete player (site admin) | `<body>` | "Home" |

The two menus (account, League actions) return focus correctly.

**Member impact:** a keyboard user who backs out of "Leave league" is thrown to the top of the page
and has to Tab back through the whole header to find their place.

**Fix:** the TabBar pattern — keep a ref to the opening control and focus it in
`onCloseAutoFocus` — in one shared wrapper, so the next dialog cannot miss it.

## Checked and found nothing material

## Proposed batches

## Owner decisions

## Doc corrections

## What this pass did not do

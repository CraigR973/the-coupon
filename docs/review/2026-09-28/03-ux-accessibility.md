# 03 — UI/UX and accessibility (objective checks only)

Working notes, every script and all raw output: `notes/03-ux/` (`progress.md` is the resume
file). Screenshots: `screenshots/`, lens-03 block of `screenshots/INDEX.md`.

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

**Coverage.** axe-core 4.10.2 ran **354 times** — every screen route in `App.tsx` (38 distinct
paths: the six public routes, the install gate, 17 member routes, five league-admin and seven
site-admin screens; the redirect-only routes render those same pages and were not swept twice),
each in **both themes at 390×844 and 1280×800**, plus loading, error, forced-empty, first-run,
offline, locked, settled, archive and not-authorised states. Every violating run was re-run from a
fresh context before being recorded (22 re-runs, all reproduced; `axe/*-rerun/`). Beside axe:
focus-ring contrast from rendered pixels at 630 Tab stops (`focus.mjs`), obscured-focus hit-testing
(`obscured.mjs`), a counted keyboard walk and every dialog's Escape behaviour (`keyboard*.mjs`),
reflow at 320 px and under the WCAG 1.4.12 text-spacing override on 36 routes, 200% zoom, target
sizes on 72 route × width combinations, reduced motion, toasts against the tab bar, and the offline
pick queue (`probe.mjs`, `toasts.mjs`, `offline*.mjs`). The corpus is 422 captures with a sha256 and
a DOM proof of state for each; the only duplicate hashes left are findings (UX-25).

## Result

| rule | impact | where | nodes |
| --- | --- | --- | --- |
| `color-contrast` | serious | a lost pick at `opacity-60`: settled coupon (UX-18) and player profile (UX-21) | 58 |
| `page-has-heading-one` | moderate | player and career profile, loading and error (UX-23) | 16 |
| `region` | moderate | the phone install gate (UX-22) | 12 |

Zero `button-name`, `link-name`, `label`, `aria-*`, `image-alt`, `document-title`,
`html-has-lang` or `landmark-one-main` violations anywhere, including all admin screens and every
state. Everything that matters most in this pass is invisible to axe: focus position and ring
clipping (UX-28, UX-29), dialog focus return (UX-30), the offline tap (UX-31), error states that
look empty (UX-25) and layout defects (UX-24, UX-26, UX-27, UX-32).

## Prior findings

Every row was re-driven against the running bundle, not re-read.

| id | batch | status | evidence |
| --- | --- | --- | --- |
| UX-14 focus indicator | 158 | **partial** | Ring now measures **4.72:1 light / 7.62:1 dark** (lowest passing stop 3.77:1) at 599 of 630 Tab stops across nine pages, both themes, both widths, from rendered pixels. But the ring is never drawn on the "How scoring works" toggle and is clipped in scroll strips (UX-29), and the selection buttons are hidden behind the tab bar when focused (UX-28). `notes/03-ux/focus/focus-summary.tsv` |
| UX-12 public-page landmarks | 137 | **held** | `/forgot-pin`, `/set-pin`, `/join/:token`, `/welcome`: zero `landmark-one-main`, `region`, `page-has-heading-one` in 16 runs (both themes, both widths). The same component rendered as the phone install gate is not covered — UX-22 |
| UX-13 opacity on tuned text | 138 | **held** | team-season kick-off 5.08:1 light / 5.60:1 dark; season-strip "now" 5.08 / 5.60 (rendered pixels, `probe-contrast.txt`); axe clean on team-season and the standings archive in all 8 runs. The results-day carousel's only opacity is `opacity-40` on a *disabled* arrow, which WCAG exempts |
| UX-15 reflow / text spacing | 167 | **partial** | The pick-market labels no longer clip at 320 and no route scrolls sideways at 320. But at 320 the home stat labels, the standings `<h1>` and profile fixture lines are cut with an ellipsis, three routes scroll sideways under text spacing, and the home labels are cut even at 390 (UX-32). `probe-reflow.txt` |
| UX-16 More-sheet Escape | 167 | **held** for the sheet | Escape returns focus to "More" (`:focus-visible`), focus contained (0 escapes in 12 Tabs). Five other dialogs still drop focus to `<body>` — UX-30 |
| UX-17 assertive failures | 167 | **held** | error and warning toasts land in the `role="alert"` region, successes in `role="status"` (17 failure/warning and 4 success captures, `toasts.txt`, `toasts-conflict.txt`). No real screen reader was run |
| UX-18 payout at `opacity-60` | **none** | **not fixed** | Settled coupon lost leg (`PickRow.tsx:238`): axe `color-contrast` on 4 of 4 runs, re-run — member name 2.90 light / 3.24 dark, fixture line and "0 pts" **2.39 / 2.76**, "Lost" badge 2.80 / 2.68. Locked-round "WIN N PTS" caption (`PickCard.tsx:343`): **2.40:1 light, 2.81:1 dark** (was 2.38 / 2.83) — though that one sits in a disabled button, which WCAG 1.4.3 exempts. `axe/settled/coupon--settled--*.json`, `probe-contrast.txt` |
| UX-19 two small links | 168 | **held** | "Forgot PIN?" 316×24, "About & scoring rules" 358×24 (`offline.txt`) |
| UX-20 200% zoom chrome | 168 | **partial** | Desktop header kept at 640×400 CSS (1280 @ 200%); content gets 343 of 400 px. But the header overflows by 79 px and pushes the account menu off-screen — UX-27 |
| UX-01 pinch-zoom | — | held | served `index.html` viewport meta has no `user-scalable` or `maximum-scale` |
| UX-04 disclosure target | — | held | no target on the round page under 24 px (targets probe, 390 and 1280) |
| UX-07 login/register landmark + `<h1>` | — | held | axe clean on both, 8 runs |
| UX-08 avatar initials contrast | — | held | no avatar node in any of the 58 contrast nodes |

Tally over the 13 rows: **9 held** (UX-12, 13, 16 for the sheet, 17, 19; spot checks UX-01, 04,
07, 08), **3 partial** (UX-14, 15, 20), **1 not fixed** (UX-18), **0 regressed** — though two new
findings are regressions introduced by fixes: UX-26 by Batch 164 and UX-27 by Batch 168.

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| UX-31 | MED | live | verified | Going offline with the app open turns a tap into a silent, endless spinner; the offline queue's messaging never shows |
| UX-28 | MED | live | verified | Keyboard focus lands behind the tab bar and the sticky header — the selection buttons themselves are hidden |
| UX-25 | MED | live | verified | Six more screens show a failure as empty, blank or loading — the coupon says "No coupon this week yet" |
| UX-30 | MED | live | verified | Escape on five dialogs drops focus onto the page body |
| UX-22 | MED | live | verified | The phone install gate is outside any landmark and the sign-in form behind it is still live |
| UX-21 | MED | live | verified | A lost pick is dimmed below AA on the player profile (same defect as UX-18) |
| UX-33 | LOW | live | verified | Claiming a pick drops keyboard focus to the page body |
| UX-29 | LOW | live | verified | The focus ring is never drawn on "How scoring works" and is clipped in scroll strips |
| UX-26 | LOW (design: med) | live | verified | The tab bar's "current" marker sits two tabs to the right on every phone screen (Batch 164) |
| UX-24 | LOW (design: med) | live | verified | "Football Stats" wraps in the tab bar and crushes its icon to 20×8 |
| UX-32 | LOW (design: med) | live | verified | The home stat labels are cut off at 390 ("PICKS …", "WIN RA…") |
| UX-27 | LOW | live | verified | At 200% zoom the header overflows by 79 px and pushes the account menu off-screen (Batch 168) |
| UX-23 | LOW | live | verified | The two profile pages have no `<h1>` while loading or failed |

All thirteen are on current `main`, which production serves (web at `4121cf0`, per the common
brief), so all are **live**. None is rated HIGH: the nearest candidates, UX-31 and UX-25, both
leave a working path (the pick still lands on reconnect; a reload recovers the round), which is
what the rubric's MED describes.

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
  "Current round / Season" sub-nav (1280), "Back" and two or three form fields on league settings (both
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

## UX-31 · MED · live · verified — going offline with the app open turns a tap into a silent spinner

Batch 90 built an offline path for picks: `sendRequest` refuses to start while
`navigator.onLine` is false, `usePickEditor` holds the pick as `queued`, shows "You're offline —
we'll send this pick the moment you're back", marks the selection "waiting to send", and
`OutstandingPickNotice` offers Send now / Discard. **None of it runs when the connection drops while
the app is open**, because the pick mutation (`usePickEditor.ts:351`) uses TanStack Query's default
`networkMode: 'online'`: the query client hears the browser's `offline` event and *pauses* the
mutation before `mutationFn` is ever called.

Driven with Chromium's offline emulation on an open round (`offline.mjs`, `offline_verify.mjs`), in
all five runs: the tapped selection shows a spinner, **every selection on the card is disabled**,
**no toast, no "waiting to send" marker, no notice, and 0 POSTs** after 8 seconds offline. On
reconnect the paused mutation fires once and the pick lands ("Grabbed Chelsea @ 4.30"). Evidence:
`notes/03-ux/offline-verify.txt`, `screenshots/current-round--offline-queued--390--dark.png`.

The designed path is still reachable when the app *starts* offline (the query client assumes online
until it hears an event), which is presumably why the 2026-09-13 review saw the right messaging.

**Member impact:** a member who taps a pick in a dead spot sees a spinner that never resolves and a
card they cannot change, with nothing telling them the pick is waiting — and if they close the app,
it is gone without their ever having been told it was not sent.

**Fix:** `networkMode: 'always'` on the pick mutation, so the app's own offline handling (already
written and tested) decides; add a prod-bundle test that goes offline *after* load.

## UX-32 · LOW (design: med) · live · verified — the home stat labels are cut off on a phone

The three hero statistics on home ("Points", "Picks won", "Win rate", Batch 151's unified
component) use `truncate` with `tracking-[0.25em]` in a third of the card: at **390** the labels
render as "PICKS …" and "WIN RA…" (`screenshots/home--offline--390--dark.png`, any home capture at
390), and at 320 even "Points" is cut (`probe-reflow.txt`: 61px of text in 51px). The same probe
finds the standings page `<h1>` (the league name) cut at 320 (251 in 186 px) and the player
profile's fixture lines cut with no other way to read them.

**Fix:** let the label wrap or drop the letter-spacing at the narrow breakpoint; never `truncate`
an `<h1>`.

## UX-33 · LOW · live · verified — claiming a pick drops keyboard focus to the page body

In the keyboard walk, Enter on a selection claims it — and focus goes to `<body>`
(`keyboard.json`, last step). The selection buttons are `disabled` while the request is in flight
(`busy`) and the claimed one stays disabled as "mine", so the focused element disables itself and
the browser drops focus. The next Tab starts again at the top of the header.

**Fix:** keep the claimed selection focusable (`aria-disabled` instead of `disabled`, or move focus
to the coupon summary on success).

## The keyboard walk, in one number

**32 keystrokes** from a signed-out `/login` to a saved pick at 1280: 23 navigation keys (Tab and
Enter) plus 9 typed characters ("Carol", "1234"). The 2026-09-13 figure was 29 and did not say
whether typing was counted. Every Tab stop matched `:focus-visible` and drew a ring. The long part
is the round page: **15 Tabs** from arriving to the first selection — five header links, the theme
toggle, the account menu, the sub-nav, the gameweek arrow, the coupon toggle, "Copy text", "How
scoring works", the competition header and two form buttons. There is no skip link; the `<main>`
landmark satisfies SC 2.4.1, but a "Skip to picks" link would cut the walk by a third.

## Checked and found nothing material

- **Accessible names: zero unnamed controls** on every route and state, both themes, both widths
  (no `button-name`, `link-name`, `label`, `aria-*-name`, `select-name` in 354 runs). Icon-only
  controls ("Older gameweek", "Switch to light mode", "Account menu (…)") are all named.
- **Toasts clear the tab bar** (Batch 149 held): at 390 every toast's bottom edge is **15 px above
  the tab bar**; with a simulated 34 px safe-area inset it moves up with the bar (110 px from the
  viewport bottom); at 1280, 32 px from the bottom. 21 captures, both themes.
- **Error states where Batch 149 put them are real**: home, standings, results, football, career
  profile and team season render `query-error-state` with a working "Try again" on a 500 (24 runs).
- **Loading states are shaped** (13 routes × 4, every capture has `aria-busy` skeletons in the DOM).
- **prefers-reduced-motion works everywhere motion exists**: with `no-preference`, navigation runs
  the indicator slide (260 ms), `page-enter` (220 ms), two `shimmer`s and one smooth scroller; with
  `reduce`, **0 animations and 0 smooth scrollers** on all five routes, before and after navigation.
- **Targets**: **zero WCAG 2.2 SC 2.5.8 failures** across 72 route × width runs once the spacing and
  inline exceptions are applied. Controls under 24 px that pass by spacing: "Back" / "Back to sign
  in" / "Leagues" back-links (15-16 px high), "Create account" (inline), two native 13 px
  radios on `/admin/results`, the "Generate new code" text button.
- **No horizontal page scroll at 320** on any of 36 routes; no page error in any run.
- **Menus**: the account menu and League actions menu open from the keyboard, move focus in, and
  return it to the trigger on Escape.

## Primary actions under 44 px (against the brief's 44 px; all pass 2.5.8's 24 px)

Selection buttons (52 px), tab-bar items (60 px) and the default `Button` (44 px) clear 44. Those that do not: the segmented sub-nav ("Current round" /
"Season", 30 px) and season-strip chips (30 px); the desktop header links (32 px, 1280 only); "+ New"
on My Leagues (36 px); and the admin row actions — Approve / Reject / Share invite / Copy / Revoke /
Reset PIN / Delete / Settle round / Run now / New join code (36 px), Promote / Remove (28 px),
"All UK leagues" (28 px); settings' notification switches (44×24).

## What the gate would and would not have caught

`apps/web/e2e/prod-bundle-*.spec.ts` (run by `scripts/run-prod-bundle-smoke.sh`, Desktop Chrome
1280×720) builds against `https://api.example.invalid`, so it can only reach the **six public
routes**. `prod-bundle-a11y` runs three rules (`landmark-one-main`, `page-has-heading-one`,
`region`) on those six in both themes; `prod-bundle-reflow` checks clipping and page overflow on the
same six at 320 px (no theme). The authenticated journey (`coupon-flow`) takes screenshots but runs
no accessibility rule. So the gate covers UX-12 and part of UX-15 and nothing else in this register:
no signed-in route, no 390 or phone UA (UX-22), no `color-contrast` (UX-18, UX-21), no focus
position or ring pixels (UX-28, UX-29), no dialog focus return (UX-30), no offline-after-load
(UX-31), no error-state assertion outside the six Batch 149 pages (UX-25), no layout geometry of the
tab bar (UX-24, UX-26) or 640 px header (UX-27). A seeded signed-in sweep — this pass's
`sweep.mjs` shape against the e2e server the coupon flow already starts — is the cheapest way to
close most of that.

## Proposed batches

All web-only; none carries API or migration.

1. **Lost-pick opacity below AA** — UX-18 + UX-21: drop `opacity-60` from `PickRow.tsx:238` and
   `PlayerProfilePage.tsx:160` (and review `PickCard`'s `opacity-55/60` captions). Web-only.
2. **The offline tap** — UX-31: `networkMode: 'always'` on the pick mutation + an offline-after-load
   prod-bundle test. Web-only.
3. **Keyboard focus management** — UX-28 (`scroll-padding`), UX-30 (one dialog wrapper that returns
   focus), UX-33 (claimed selection keeps focus), UX-29 (inset ring where clipped). Web-only.
4. **Error ≠ empty, everywhere** — UX-25: `QueryErrorState` on the round, My Leagues, league members
   and activity, admin players and dashboard. Web-only.
5. **The phone gate as a page** — UX-22 (+ UX-23 while in the shell): `landmark`, `inert` behind it.
   Web-only.
6. **Tab bar and narrow-width polish** — UX-26 (`left-0`), UX-24 (label), UX-32 (stat labels, h1),
   UX-27 (header between `sm` and `md`). Web-only; pairs with lens 06.
7. **Signed-in accessibility sweep in the gate** — tooling-only: axe `color-contrast` + the three
   landmark rules on the seeded signed-in routes at 390 and 1280, plus obscured-focus and
   offline-after-load checks.

## Owner decisions

1. **UX-18's locked-round caption.** "WIN N PTS" in a locked round sits in a disabled button
   (2.40 / 2.81:1), which WCAG exempts. Options: (a) leave it — it is an inactive control; (b) lift
   it to `text-text-muted` at full opacity like the odds beside it, which already pass (4.70 /
   6.45:1). **Recommend (b)**: members read that figure after lock to see what the week could have
   paid, so it is information rather than a control label, and the fix is one class.
2. **44 px vs 24 px.** Every target passes WCAG 2.2 AA (24 px); the brief's 44 px is Apple's HIG.
   Options: (a) 24 px is the bar; (b) 44 px for primary member actions only (sub-nav, season chips);
   (c) 44 px everywhere including admin. **Recommend (b)**: the 30 px sub-nav and season chips are
   member-facing and tapped weekly; admin rows are used by one person at a desk.

## Doc corrections

- `docs/review/2026-09-28/notes/harness/web.sh` (the lead's harness, not a repo doc): builds with
  the wrong working directory, so Tailwind's cwd-relative `content` globs match nothing and the
  bundle is unstyled (9.1 KB CSS vs 45.8 KB). From: `vite build "$ROOT/apps/web"` run from the
  caller's cwd. To: run it with `cwd=apps/web` (as `notes/03-ux/build_web.py` does), and refuse a
  stylesheet under 30 KB. Lenses 02 and 05 already label their captures from it "unstyled".
- No repository document was found stating something this pass disproved. `session-log.md`'s Batch
  168 entry says the 640-px layout "keeps the main navigation" — true; it does not say the header
  fits, and it does not (UX-27).

## What this pass did not do

- **No real screen reader.** WebKit will not install here and VoiceOver cannot be driven headlessly;
  UX-17 and UX-22 state what the DOM exposes, not what VoiceOver says. Five minutes of the owner's
  time with VoiceOver on the pick flow and the phone gate is still the best check left.
- **No real phone and no standalone mode.** 390 captures use a desktop UA at 390×844; safe-area
  insets were simulated by overriding `--safe-bottom`. The install gate was driven with an Android
  UA only.
- **No Windows forced-colours check.** The ring is a box-shadow over Tailwind's `outline-none`
  (a transparent outline), which should survive forced colours, but it was not run.
- **The real claim race was driven only once** before Bob's per-member pick limit (10/hour,
  in-process) was spent; the four conflict captures replay the API's exact 409
  `SELECTION_TAKEN` refusal, and the price-moved, busy and 500 captures are fulfilled responses of
  the API's shapes. All four feedback states are in the corpus (lens 06 may re-take them).
- **No colour-blindness simulation** and no Lighthouse accessibility score (the axe rules are the
  same engine).

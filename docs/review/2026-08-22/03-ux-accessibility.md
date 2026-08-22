# 03 — UI/UX and accessibility

Method: the real app, built from `main`, served by the Vite dev server against a
local `tests.e2e_server` API on seeded data. axe-core 4.10.2 injected into the
live page at 390x844 — so unlike `test/accessibility.test.tsx`, colour contrast
was evaluated against real computed styles rather than skipped.

## UX-01 · CRITICAL · Pinch-zoom is disabled app-wide
`apps/web/index.html:30`

    content="width=device-width, initial-scale=1.0, maximum-scale=1.0,
             user-scalable=no, viewport-fit=cover"

`maximum-scale=1.0, user-scalable=no` is the only axe violation on every screen
audited, and axe rates it **critical**. It is a straight WCAG 2.1 AA failure
(1.4.4 Resize Text) and it lands on the audience least able to absorb it: this
is a phone-first PWA whose core screen is a dense grid of two-decimal odds at
10px. A member with low vision cannot enlarge any of it.

The usual reason for this attribute is stopping iOS Safari zooming when an input
takes focus — but the fix for *that* is a ≥16px font-size on inputs, not
withdrawing zoom from the whole document.

## UX-02 · HIGH · The light theme fails AA nearly everywhere it uses muted text
21 failing nodes **on the pick screen alone**, over five token pairs. Computed
from the tokens in `apps/web/src/index.css` and confirmed live by axe:

| pair | ratio | need | where |
| --- | --- | --- | --- |
| `--text-muted #8A93A1` on `--surface-elevated #F1F3F5` | **2.78** | 4.5 | 6 nodes |
| `--text-muted #8A93A1` on `--surface #FFFFFF` | **3.10** | 4.5 | 7 nodes |
| `--text-muted #8A93A1` on `--bg #F7F8FA` | **2.91** | 4.5 | 1 node |
| `#F59E0B` (warning) on `#FFFFFF` / `#F7F8FA` | **2.14 / 2.02** | 4.5 | 2 nodes |
| `--primary #059669` as text on `#FFFFFF` / `#F7F8FA` | **3.76 / 3.54** | 4.5 | 3 nodes |
| `#28A47E` on `#F1F3F5` | **2.81** | 4.5 | 1 node |

`--text-muted` in light mode fails against **every** surface tier the palette
defines. The amber pair is the worst of it and carries the single most important
status line in the product — "You haven't grabbed a selection yet" — at 2.14:1.

The dark palette was clearly the design target and was verified: `index.css:87`
records the on-primary/on-accent checks explicitly. Light mode never got the same
pass.

Minimum correction that clears 4.5:1 on every light tier: `--text-muted:#666F7D`
(4.57 / 4.78 / 5.08).

## UX-03 · MED · Dark-mode muted text fails on the two upper surface tiers
Same token, other palette. `--text-muted #7B859B` measured against each tier:

    bg               #0B0E13   5.22  PASS
    surface          #131720   4.84  PASS
    surface-elevated #1B2030   4.38  FAIL
    surface-overlay  #242938   3.91  FAIL

So it was checked against the two lower tiers and shipped, and it fails wherever
a card sits on a card — which is where the pick screen puts every "WIN n PTS"
line, the competition chip, and the inactive tab-bar labels. `#8690A6` is the
smallest lift that clears both (5.06 / 4.52) and stays visually distinct from
`--text-secondary #94A3B8`.

## UX-04 · MED · Touch targets below the WCAG 2.2 minimum
Measured live at 390px. WCAG 2.2 SC 2.5.8 (AA) requires 24x24 CSS px; Apple HIG
and Material both ask 44x44 / 48x48.

| control | size | verdict |
| --- | --- | --- |
| form disclosure, `FormLine` (Batch 53) | **70 x 22** | **fails 2.5.8 AA** |
| sub-nav "Your pick" / "Combined coupon" / "Results" | 78-126 x 30 | passes 2.5.8, under HIG |
| account menu avatar button | 32 x 32 | passes 2.5.8, under HIG |

The form disclosures are the only outright AA failure, and they are new — Batch
53 made the pips interactive without giving them a target to match.

## UX-05 · LOW · The home screen is one card and ~900px of nothing
At 390x844 the signed-in home surface renders a single league card and then
empty background to the tab bar. It is the app's landing surface and the first
thing a member sees every time. Nothing else competes for the space — no next
kick-off, no recent result, no what-other-members-did.
Judgement call, not a defect; recorded so it is a decision rather than an
oversight.

## UX-06 · LOW · Four stacked info blocks before the first fixture
Pick screen order: countdown, "HOW SCORING WORKS", "n of 3 picked", "You haven't
grabbed a selection yet", *then* collapsed competitions. On the one screen whose
job is to take a pick, the primary action starts below the fold and behind a
disclosure. With two competitions seeded the collapse costs two taps to reach
one fixture each.

## Verified good
* Focus rings are strong and visible (`focus-visible:border-primary` +
  `shadow-glow`) — genuinely better than most apps of this size.
* `PinInput` handles rapid typing and paste correctly; it keeps a
  `latestValue` ref precisely to beat React's async state, and
  `components/__tests__/PinInput.test.tsx` covers both. An early suspicion that
  it dropped digits was an artifact of the automation, not a defect.
* Every interactive element carries an accessible name; axe found no
  `link-name`, `button-name`, `label` or `aria-*` violations on any screen.
* Form pips are visible at mobile width — Batch 52's fix holds.
* Only one axe violation exists in dark mode across the audited screens.

## Environment note — not a product finding
Under `vite preview` over plain HTTP with a cross-origin API, the Workbox
service worker's own `fetch` returned 200 while the page-level request failed
`net::ERR_FAILED`. It did not reproduce on the dev server and production is
live and serving members, so this is an artifact of the local insecure-origin
preview. Recorded only so the next person does not chase it.

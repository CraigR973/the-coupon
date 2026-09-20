# 03 — UI/UX and accessibility (objective checks only)

Method: the production bundle served against a seeded local API, driven in real
headless Chromium. axe-core 4.10.2 was injected into the live page and run across
**88 route/state runs** — every route in `App.tsx` including the public pages,
the league-admin pages and all eight site-admin screens, in both themes at
390×844. Screenshots were captured for every screen and state at **390×844 and
1280×800 in both themes**; the corpus is `screenshots/` (173 files, indexed by
`screenshots/INDEX.md`) and is what lens 06 judges.

## Result: 53 violating nodes, from two root causes

| rule | impact | screens | nodes |
| --- | --- | --- | --- |
| `landmark-one-main` | moderate | forgot-pin, set-pin, join, welcome (both themes) | 8 |
| `region` | moderate | same four screens (forgot-pin 5, set-pin 7 per theme) | 28 |
| `page-has-heading-one` | moderate | forgot-pin, set-pin, join (both themes) | 6 |
| `color-contrast` | **serious** | standings archive, team season (both themes) | 6 |

Everything else was clean: no `link-name`, `button-name`, `label`, `aria-*`,
`image-alt` or `html-has-lang` violations anywhere, on any screen or state,
in either theme — including all eight admin screens and every error, empty,
loading, offline and archive state captured.

One run initially reported `document-title` and `html-has-lang` failures on the
empty-results state in dark mode. That was a capture artefact — a dead database
process under a live holder — and re-running it produced a correctly rendered
page with **zero** violations. It is excluded from the findings and recorded
under "where this review was wrong".

## Prior register — spot-checked

| id | holds? | evidence |
| --- | --- | --- |
| UX-01 pinch-zoom | yes | no `user-scalable=no` |
| UX-04 disclosure target | yes | still ≥24px |
| UX-07 login/register landmark + `<h1>` | yes — **on those two screens only** | see UX-12 |
| UX-08 avatar initials contrast | yes | no avatar contrast node anywhere in 88 runs |
| Batch 111 club-link target | yes | passes |

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| UX-12 | MED | live | verified | Four more public screens render outside the app shell — Batch 86 fixed only login and register |
| UX-13 | MED | live | verified | A 70% opacity applied over already-tuned text tokens drops two surfaces below AA |

## UX-12 · MED · live · verified — the landmark fix never reached the rest of the auth family

`/forgot-pin`, `/set-pin`, `/join/:token` and `/welcome` have no `<main>`
landmark, no level-one heading, and content sitting outside any landmark — the
exact defect Batch 86 fixed for login and register. That batch's scope boundary
said "these two pages' shell only", so its four siblings were never brought
along. `/set-pin` is the worst (seven orphaned regions per theme), and it is the
screen a member lands on after a PIN reset — the recovery journey.

**Member impact:** a member recovering their PIN or opening an invite link gets a
page a screen reader cannot navigate by landmark or heading.

**Fix:** wrap all four in the same `<main>` + `<h1>` shell Batch 86 applied, or
move them inside the shared layout.

## UX-13 · MED · live · verified — opacity stacked on top of tuned colour

Two surfaces apply a 70% opacity to text that already sits at exactly the AA
threshold, which pushes it under:

- the team-season kick-off time — **2.83:1** light, 3.4:1 dark
- the season strip's "now" badge — **3.57:1** light, 4.05:1 dark

Both need 4.5:1. This is the same class of mistake the palette work fixed twice
before (a colour tuned on one surface, reused on another), reappearing as an
opacity utility rather than a token. A related use on the results-day carousel
was spotted but not measured.

**Member impact:** the kick-off time on the team page and the marker for the
current season are hard to read, worst in light mode.

**Fix:** remove the opacity and use the existing muted-ink token, or add a token
that is AA at the opacity actually rendered.

## What the gate would and would not have caught

The repository's own accessibility smoke runs against the production bundle but
covers a small set of routes; none of the four screens in UX-12 is among them,
and its contrast assertions do not reach the team-season page or the archive
state. Both findings are invisible to the gate as configured, which is why they
survived to this review.

## Proposed batches

1. **Four public screens still render outside the app shell** (UX-12) — web-only.
2. **A 70% opacity drops two AA-tuned surfaces below contrast** (UX-13) — web-only.
3. **Extend the accessibility smoke to every public route and both themes** so this class stops escaping — tooling-only.

## What this pass did not do

**The manual pass was not completed** — the keyboard-only walk, focus-ring
contrast, accessible-name sweep of the live accessibility tree, 200% zoom and
320px reflow, text-spacing, reduced-motion emulation and the 44px target
measurements were all cut short by usage limits. They are listed in
`08-sequencing.md` as the first thing to finish. The axe sweep and the corpus are
complete; the manual half is not, so this document is an incomplete lens and
should not be read as "the app passes everything else".

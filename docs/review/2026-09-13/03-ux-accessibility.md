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
| UX-14 | HIGH | live | verified | Keyboard focus is invisible on every button — the ring measures 1.3-1.5:1 where 3:1 is required |
| UX-12 | MED | live | verified | Four more public screens render outside the app shell — Batch 86 fixed only login and register |
| UX-13 | MED | live | verified | A 70% opacity applied over already-tuned text tokens drops two surfaces below AA |
| UX-15 | MED | live | verified | Pick-market labels clip at 320px, and three more elements clip under the text-spacing override |
| UX-16 | MED | live | verified | Escape on the bottom-nav sheet drops focus onto the body instead of returning it |
| UX-17 | MED | live | verified | A failed pick is announced no more urgently than a successful one |
| UX-18 | MED | live | verified | The locked/settled payout figure sits at 2.4-2.8:1 |
| UX-19 | LOW | live | verified | Two text links fall under the 24px minimum target |
| UX-20 | LOW | live | verified | At 200% zoom the desktop layout reverts to mobile chrome eating a third of the viewport |


## UX-14 · HIGH · live · verified — keyboard focus is invisible on every button

`button.tsx:11` sets `focus-visible:outline-none` and replaces the native outline
with `focus-visible:shadow-glow`, where `--shadow-glow` is
`0 0 0 3px rgba(16, 185, 129, 0.25)` — a ring at 25% alpha. Measured from
rendered pixels against the background it sits on: **1.49-1.53:1 in dark,
1.27-1.28:1 in light**, against the 3:1 that WCAG 2.2 requires of a focus
indicator. Text inputs pass (7.07 and 3.77) but only because they additionally
get `focus-visible:border-primary`; buttons have no such second signal.

This is the single most consequential accessibility finding in the review, and
it is exactly what the automated sweep could never catch: **axe has no
focus-indicator rule**, so 88 clean runs said nothing about it.

**Member impact:** anyone navigating by keyboard cannot see where they are —
including on the selection rows and the pick action, the one thing the product
exists to do.

**Fix:** give buttons the same treatment inputs already have — a solid ring that
clears 3:1 in both themes — or drop `outline-none` and style the native outline.
Reuse the border token rather than inventing a colour, so contrast cannot drift.

## UX-15 · MED · live · verified — labels clip at the narrow end

At 320 CSS px the pick-market labels overflow their container: "No — not both
score" needs 106px in a 68px box. Under the WCAG 1.4.12 text-spacing override
three further elements become newly clipped. The page body itself never scrolls
horizontally at 320 or 640 — the layout holds; it is the labels inside it that do not.

**Fix:** let the market labels wrap or shorten at the narrow breakpoint.

## UX-16 · MED · live · verified — Escape loses the keyboard user's place

Closing the bottom-navigation "More" sheet with Escape leaves focus on `<body>`,
so the next Tab starts from the top of the document. The account menu does this
correctly and is the model to copy.

## UX-17 · MED · live · verified — a failed pick is announced as calmly as a successful one

Error toasts share sonner's single polite live region with successes. Nothing
carries `role="alert"` or an assertive region, so a screen reader finishes what
it is saying before mentioning that a pick did not land. Paired with the
correctness finding that a lost race currently arrives as a network error, a
screen-reader user is the last to know.

**Fix:** render failures into an assertive region.

## UX-18 · MED · live · verified — the payout figure is the least readable number on the card

On locked and settled rounds the "win N pts" payout renders at `opacity-60`,
measuring **2.83:1 dark and 2.38:1 light**. This is the same defect family as
UX-13 — opacity stacked on an already-tuned token — and the two should be fixed
together rather than as separate batches.

## UX-19 and UX-20 · LOW

**UX-19** — "Forgot PIN?" renders 316×**16** and "About & scoring rules"
358×**20**, both under the 24px minimum of WCAG 2.2 SC 2.5.8. "Create account"
is inline text and exempt. Batch 55's and Batch 111's earlier target fixes both
still hold.

**UX-20** — at 200% zoom on a 1280 viewport the layout falls back to mobile
chrome, which then consumes 142px of the 450px usable height — a third of the
screen given to navigation.

## The keyboard walk, in one number

**29 keystrokes** from page load to a saved pick. There is no submit button —
the flow autosaves — so that count is the whole journey: sign in, navigate,
expand a collapsed competition group, and choose. The collapsed-by-default
groups (a design finding, DES-02) are what make it long.

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

## Checked and found nothing material

**0 unnamed controls** across eight routes — every button, link and input has an
accessible name, including the icon-only ones. **0px horizontal page scroll** at
both 320 and 640 CSS px. The lock countdown is **not** inside a live region, so
it does not announce every second — the screen-reader trap this pass went
looking for is not there. `prefers-reduced-motion: reduce` genuinely works: live
animations drop 15 to 0 and smooth scrollers 1 to 0, and a real
`@media (prefers-reduced-motion)` block exists at `index.css:419`. Batch 55's
form-disclosure target and Batch 111's club-link target both still pass. Every
won/settled badge measures 5.02-8.35:1.

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

**No real screen-reader run.** WebKit cannot be installed on this machine and
VoiceOver cannot be driven headlessly, so the live-region findings (UX-17) state
what the markup declares, not what a screen reader actually says. Worth an
owner's five minutes with VoiceOver on the pick flow.

The cause of the standings screen's blocking time is a performance question and
is recorded in `04-performance-operations.md`, not here.

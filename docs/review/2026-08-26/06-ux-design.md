# 06 — Visual design ("does this look premium")

The subjective half `03-ux-accessibility.md` deliberately left out. Method: I read
all 20 screenshots that document captured (10 screens × light/dark, 390×844,
post-settlement state so result/standings/form surfaces have real content) and
judged them against a "professional product, not a hobby project" bar — the
standard the owner asked for, not a specific competitor.

## The headline: the design system itself is good. The execution is unfinished in two specific, fixable ways.

This is not a generic "make it look nicer" note. The typography (a tracked
uppercase label style used consistently for section headers — "SEASON
STANDINGS", "RESULT · GAMEWEEK 1"), the brand mark (the ticket icon + gold
serif "THE COUPON" wordmark), the card system, the pill badges, and the accent
green are all deliberate, consistent, and better than most side projects reach.
Both themes hold together — dark mode is not just an inverted light mode, it
has its own considered near-black surfaces. `login`/`register` are the
strongest screens in the set: wordmark, tagline ("One pick. One coupon. Every
Saturday."), and a clean card read as a real product's front door, not a form.

What's holding the rest back from "looks expensive" is two concrete, recurring
problems, not a vague polish deficit:

### 1. Every core screen ends far short of the viewport, and it reads as unfinished, not minimal

`light-home.png`, `dark-home.png`, `light-standings.png`, `dark-standings.png`
all end their real content within the top third of a 390×844 screen and leave
the rest empty background. This isn't a one-off — it is the single most
repeated visual signal across the whole screenshot set, and it directly
undercuts the "premium" goal: a screen that stops 250px in with nothing below
it reads as a beta, not a $30k build, no matter how good the typography above
the fold is. This restates the prior review's UX-05, which `03-ux-accessibility.md`
already confirms is "largely stale" content-wise after Batches 79–81 added the
result panel and form line — but the screenshots show the *layout* problem
outlived the content fix. The content got richer; the page didn't get
redesigned to use the space it now has data for.

### 2. A football product with no football imagery anywhere

Not one screenshot — pick screen, coupon, standings, results — shows a club
crest, competition badge, or any imagery at all. Every fixture is rendered as
plain text ("Arsenal · Chelsea"). For a product whose entire subject is
football fixtures, this is the highest-leverage single visual addition
available: crests are the fastest, most universally legible signal of
"this was built by people who take the sport seriously" that a football
product can carry, and their absence is likely the single biggest reason the
app reads as a spreadsheet-with-a-brand rather than a sports product, despite
the actual typography/color work being solid. This needs an explicit decision
from the owner before it's a batch — club crests are typically trademarked
assets, and sourcing/licensing them (or using a neutral team-initial badge
system instead of real crests) is a product and legal call, not a pure
engineering one.

## Secondary observations

- **Avatars are the only imagery in the app**, and they're plain two-letter
  initials on a flat colour — clean and consistent, but generic. `03-ux-accessibility.md`'s
  serious accessibility finding (bronze-slot avatar text fails AA) also means
  this is the one piece of imagery the app has, and it has a contrast bug.
- **Settings (`light-settings.png`) is a flat, undifferentiated stack of
  same-weight white cards** — Change PIN, Timezone, Odds format, Appearance,
  Push Notifications, Notification Preferences, Install App, About, all read
  at identical visual weight with no grouping or hierarchy. Functional, not a
  correctness issue, but the page that should feel like "account settings in
  a considered app" instead feels like an unstyled form list. Low priority
  relative to the two headline issues, but cheap to improve (group into 2-3
  visually distinct sections, e.g. "Account", "Display", "Notifications").
- **The one moment of real delight in the whole set** is the combined-coupon
  win state (`light-combined-coupon.png`): "All legs won 🎉" plus a per-leg
  green "Won" badge and the frozen odds math shown plainly. This is exactly
  the kind of small, specific touch that makes a product feel cared-for — the
  app should have more moments like it, not fewer. There is currently no
  equivalent for a *losing* week or a personal-best result (see FEAT-B06 in
  `05-feature-gaps.md`, which found no share surface for a settled result).

## What this doc is not

Not a redesign proposal, not a component-by-component audit, and not a claim
that any of this blocks launch — the app is fully functional and the
underlying design system is sound. This is the "would a stranger believe this
cost real money" pass the owner asked for, reported against actual screenshots
rather than taste in the abstract. The two headline items (empty screen space,
no football imagery) are where the actual gap between "well-built" and
"premium-feeling" lives; everything else in this document is secondary to
those two.

## Register

| id | finding | disposition |
| --- | --- | --- |
| UX-07 | login/register render outside the page shell — no `<main>`, no `<h1>` | Batch 86 (see `03-ux-accessibility.md`) |
| UX-08 | avatar palette uses fill tokens as text colour — bronze fails AA, other slots unverified | **Batch 98** — solid fill with high-contrast text (owner, 2026-08-27); clears all six slots by construction rather than tuning six colours against a tint |
| UX-09 | home and standings end far short of the viewport on every screen captured | **Batch 97** — content *and* scale pass (owner, 2026-08-27). Home only; standings' sparseness was a three-member test-seed artifact |
| UX-10 | no team crests, competition badges, or any football imagery anywhere in the app | **declined** (owner, 2026-08-27) — the app stays text-only, and the visual effort goes to UX-09 instead |
| UX-11 | Settings is a flat, undifferentiated stack with no visual grouping | backlog — low priority, cheap fix whenever Settings is next touched |

**Note on UX-10's decline.** This document argued crests were the highest-leverage
single visual addition available. The owner declined them on 2026-08-27, which
makes UX-09 (Batch 97) carry the entire visual case on its own rather than
sharing it. Worth stating plainly so a future review doesn't re-propose crests as
though the idea had never been considered: it was, and it was turned down.

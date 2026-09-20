# 06 — Premium design

Judgement, but concrete. Method: the 173-image corpus in `screenshots/` — every
screen and state at 390×844 and 1280×800 in both themes — read image by image and
checked against the source for what it claimed. The bar is the finish of FotMob,
Sleeper, the official FPL app and Apple Sports, **within the owner's text-only
decision** (no crests, badges or imagery — declined 2026-08-27 and not reopened
here).

**This lens is incomplete.** The core weekly-loop screens were judged; the
peripheral screens (auth family, settings, admin console, football section) and
the PWA polish pass were not, and neither was the ranked top-ten with mockups
that the brief asked for. What follows is the core-screen half, which is enough
to act on. See "what this pass did not do".

## What already works — do not churn it

The design system underneath is genuinely good and the previous review's verdict
stands. The tracked uppercase section labels, the ticket wordmark, the card
system, the pill badges and the accent green are deliberate and consistent. Both
themes are considered — dark is not an inverted light. The pick-confirmation
state reads as intentional. Home's happy state now fills the viewport: content
reaches 81% of the 844px screen and the full-page height equals the viewport, so
**Batch 97 did what it set out to do**.

## What breaks the premium feel

| id | impact | finding |
| --- | --- | --- |
| DES-01 | high | 1280 is a phone layout stretched, not a desktop design |
| DES-02 | high | The pick screen opens with everything collapsed — no fixture, no price |
| DES-03 | high | Every pick outcome, good or bad, arrives as the same red toast |
| DES-04 | med | Toasts sit under the tab bar and ignore the safe area |
| DES-05 | med | Skeletons are generic bars and the content jumps when they resolve |
| DES-06 | med | Error states are indistinguishable from empty states and offer no retry |
| DES-07 | med | First-run home stops at 58% of the screen, and its only action is a text link |
| DES-08 | med | The same statistic is drawn two different ways on two screens |
| DES-09 | med | There is no type scale; 84 nodes render at 11px or less, four at 9px |

### DES-01 · high — the desktop layout is the phone layout, stretched

There is not a single large-breakpoint utility anywhere in the application (45
small-breakpoint and 9 medium, zero large or extra-large), and the shell pins the
same maximum width at every viewport. The current-round, leaderboard and results
pages have no responsive utilities at all. At 1280 the result is one narrow
column of phone-sized cards in a wide empty frame.

The owner has decided desktop is a supported way to play, which makes this the
largest single visual gap: the product looks unfinished to anyone who opens it on
a laptop.

**Fix:** a real two-column arrangement at the large breakpoint for the three
screens that carry lists — round beside coupon, standings beside form — and raise
the shell's maximum width. Medium effort, high impact.

### DES-02 · high — the pick screen opens closed

Arriving at the round, every competition group is collapsed. The member sees
section headings and counts, no fixture and no price, and must tap before the
screen shows anything they came for. The confirmation screenshot makes it plain:
"You haven't picked yet — grab a selection below", above two closed rows.

**Fix:** open the first competition by default (or the one holding the earliest
kick-off), and keep the rest collapsed. Small effort, high impact.

### DES-03 · high — one red toast for every outcome

Losing the race for a selection, a price that moved, the league being busy, a
genuine failure, and the reassurance that an offline pick has been queued all
arrive through the same error toast. Across the app there are 57 error toasts, 44
success, two informational, **zero warnings and zero with an action button**.

This compounds the correctness finding that a lost race currently surfaces as a
network error: even once that is fixed, the member is told in the same red voice
whether they lost a selection or the app broke.

**Fix:** a warning variant for "someone got there first" and "the price moved",
each with the action that follows (pick again, accept the new price), and an
informational variant for queued-offline. Small effort, high impact.

### DES-04 to DES-09 — the rest, briefly

**DES-04** — toasts are anchored bottom-right with no offset for the 60px tab bar
or the safe area, so on a phone they collide with the navigation.

**DES-05** — loading states are generic grey bars that do not match the shape of
what replaces them, and the content jumps 53px when they resolve. A shimmer token
exists in the stylesheet with **zero users**.

**DES-06** — an error state looks the same as an empty state: same layout, same
weight, no retry control. A member cannot tell "nothing happened yet" from
"something went wrong".

**DES-07** — first-run home ends at 58% of the viewport and its only call to
action is an inline text link. This is the first screen a new member sees, and it
is the one screen Batch 97's fill-the-viewport work never reached.

**DES-08** — the hero statistic and the card statistic are the same object drawn
five different ways, including different colours for the figure itself.

**DES-09** — the Tailwind config defines no font sizes or line heights, so type
is chosen per component. 84 nodes render at 11px or smaller and four at 9px —
below what is comfortable for odds and points on a phone.

## Where this review corrected itself

The first capture run produced screenshots for the loading, error and
pick-feedback states that were actually the idle screen — the states had not been
driven, only named. The design pass caught it, the lead confirmed it by hashing
the files and reading one image, and a re-capture was started but did not finish
before the usage limit. So **the corpus still lacks a genuine settled-results
screen, a settled combined coupon, and the four pick-feedback states**; DES-03's
judgement rests on the toast source rather than on images, and DES-05 and DES-06
rest on partial evidence. This is recorded rather than glossed because the next
design pass should re-capture before trusting those files.

## Proposed batches

1. **The desktop layout is the phone layout stretched** (DES-01) — web-only.
2. **The pick screen opens with every fixture hidden** (DES-02) — web-only.
3. **Every pick outcome arrives as the same red toast** (DES-03) — web-only, pairs naturally with the correctness fix for the claim race.
4. **Toasts collide with the tab bar; skeletons do not match their content; errors look like empties** (DES-04, DES-05, DES-06) — web-only.
5. **First-run home stops a third of the way down** (DES-07) — web-only.
6. **Define a type scale and lift the smallest text** (DES-09, with DES-08) — web-only.

None of these reintroduces imagery, and every one reuses an existing token or
raises a size, so none can regress contrast.

## What this pass did not do

The peripheral screens (welcome, login, register, forgot-PIN, set-PIN, join,
my-leagues, settings, the five league-admin screens, the eight admin-console
screens, the football section, about, offline) were not judged. The PWA polish
pass — manifest, maskable icons, splash, theme-colour per scheme, install prompt,
and **safe-area insets in standalone mode** — was not done, and the safe-area
question is a real iPhone defect risk given DES-04. The ranked top-ten with token
values, before-images and HTML mockups was not produced; the list above is
prioritised but not costed to that standard. No motion timings were measured.

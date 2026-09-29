# Lens 06 — Premium design (judgement, but concrete)

Output: `docs/review/2026-09-28/06-premium-design.md`, plus HTML mockups under
`docs/review/2026-09-28/notes/06-design/mockups/`. Notes: `docs/review/2026-09-28/notes/06-design/`.
Ports: API **8160**, web **4360**. New finding ids start at **DES-10**.

The bar is the finish of **FotMob, Sleeper, the official FPL app and Apple
Sports**, within the owner's **text-only decision** (no crests, badges or imagery
— not reopened). Lens 03 has captured a corpus in `docs/review/2026-09-28/screenshots/`
with `INDEX.md`; start from it, and **do not trust a capture until you have opened
it** — last time "loading", "error" and "feedback" captures were all the idle
screen.

## Part 1 — did the visual pass land?

Judge each against its batch row's acceptance and against the 2026-09-13 finding,
from images you have opened and from the source:

| id | impact then | batch |
| --- | --- | --- |
| DES-01 desktop is the phone layout stretched | high | 140 |
| DES-02 pick screen opens closed | high | 139 |
| DES-03 one red toast for every outcome | high | 139 |
| DES-04 toasts under the tab bar / safe area | med | 149 (final commit `4121cf0` moved the mobile offset) |
| DES-05 generic skeletons, content jump | med | 149 |
| DES-06 error looks like empty, no retry | med | 149 |
| DES-07 first-run home stops at 58% | med | 150 |
| DES-08 one statistic drawn five ways | med | 151 |
| DES-09 no type scale; 84 nodes ≤11px | med | 151 — re-count nodes by rendered size |
| focus ring (UX-14) as a visual element | — | 158 |
| targets and zoom chrome (UX-19/20) | — | 168 |

## Part 2 — finish what 2026-09-13 left undone

1. **Peripheral screens**: the auth family (welcome, login, register, forgot-PIN,
   set-PIN, join), my-leagues, settings (including the new account deletion and
   export from Batch 136), the five league-admin screens, the site-admin console,
   the football section (tables, results, team season), about, offline.
2. **PWA polish**: the manifest (`apps/web/vite.config.ts` → built
   `manifest.webmanifest`), icons including the maskable one (render it inside a
   circle and a squircle mask and look), splash/background colour, `theme-color`
   per colour scheme (both themes; the manifest pins `#071A3D`), apple-touch-icon
   and iOS meta tags, the install prompt/onboarding flow, and **safe-area insets
   in standalone mode** (emulate `display-mode: standalone` and an inset
   viewport; check the tab bar, the header and toasts).
3. **Fill the corpus gaps** and prove each: a genuine **settled-results** screen,
   a **settled combined coupon** (with a void leg, since Batch 156 changed how it
   reads), and the **four pick-feedback states** — confirmed, lost the claim
   (conflict), price moved, league busy (`PICKS_BUSY`) — plus the queued-offline
   message. Drive them for real against the stack (a second member racing a
   claim; the fake provider moving a price; the busy bucket exhausted). Hash
   every capture, list duplicates, and open each one you rely on. Append your
   rows to `screenshots/INDEX.md`.

## Part 3 — output

- **Per screen**: what works (so nobody churns it) and what breaks the premium
  feel, each with the screenshot path.
- **The ten highest-leverage changes**, ranked by impact ÷ effort, each specific
  enough to become a batch row: the token names and exact values (read
  `apps/web/src/index.css` and `apps/web/tailwind.config.ts` for the current
  tokens), the components to change (file paths), the "before" screenshot path,
  and an **HTML mockup** where it helps (self-contained HTML using the app's own
  token values; screenshot the mockup at 390 and 1280 in Chromium and save the
  PNGs beside it).
- **No recommendation may regress WCAG AA**: compute the contrast of every colour
  you propose against the surfaces it sits on, in both themes, and show the
  numbers.

## Lead's notes at launch (29 Sep ~23:40)

- **The harness `web.sh` was fixed at 18:50.** Its first version ran Vite outside
  `apps/web`, so Tailwind emitted a 9 KB stylesheet and every capture built with it is
  unstyled. It now builds from `apps/web` and refuses a stylesheet under 30 KB (45.8 KB is
  right). Captures whose file name contains `-unstyled-` (lenses 02 and 05) are text
  evidence only — never judge design from them. Lens 03 used its own `notes/03-ux/build_web.py`.
- Lens 03's corpus is **in progress** (batch 1: the open-phase states). Start from what is
  committed; capture what you need yourself rather than waiting.
- Seen by the lead in an (unstyled) settled-coupon capture: an erased member is shown as
  **"Former"** on the slate ("taken by Former · 29 Sep", "Picked by Dan, Former") — the
  first-word shortening applied to "Former member". Judge it as copy.
- Usage limits are the binding constraint on this review (three interruptions so far):
  update `progress.md` after every step, commit often, write findings into the lens
  document as they are verified, and script captures so large outputs are written to files
  rather than read back.

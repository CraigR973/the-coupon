- [ ] **Batch 169 — Every toast is unreadable in dark mode, the default theme**
  — specified from `docs/review/2026-09-28/06-premium-design.md`, DES-10 (high impact, live,
  verified). `AppToaster.tsx` renders sonner with `richColors` and no `theme`, so sonner
  draws its *light* pale fills whatever the app's theme; Batch 149's last commit (`4121cf0`,
  `index.css:430-434`) then forced every title to `var(--text-primary)`, which is near-white in
  dark mode. Title contrast measured **1.01-1.07:1** — the lost-claim warning, the price-moved
  prompt and every failure are illegible in the theme most members use. Shipped by an
  automatic close-out on 28 Sep.

  Theme the toaster from the app (`theme={resolvedTheme}`), drop `richColors`, and style the
  five variants on existing tokens — surface-overlay fill, `--text-primary` title, a 3 px
  left edge and icon in `--success-ink` / `--warning-ink` / `--error-ink` / `--primary-ink`,
  action button `bg-primary text-on-primary`; delete `index.css:430-434`. Split each message
  into a title that says what happened and a body that says what to do (`pickErrorMessage`
  already holds the body text). Values and contrast table: 06, top-ten #1; mockup
  `notes/06-design/mockups/toasts.html`.

  Verification: rendered-pixel contrast of title (≥4.5:1), body (≥4.5:1) and edge/icon (≥3:1)
  for all five variants in both themes at 390 and 1280; the role="alert"/"status" split from
  Batch 167 unchanged; a vitest that fails if the toaster renders without a theme.

  Scope boundary: toast styling and copy structure. No change to when toasts fire.
  **Web-only — ship first; it reaches members on its own close-out push.**

- [ ] **Batch 170 — The tab bar marks the wrong tab, crushes an icon, and the home figures lose their labels**
  — specified from `docs/review/2026-09-28/03-ux-accessibility.md`, UX-26, UX-24, UX-32 and
  UX-27 (LOW, design med, live, verified). The tab bar's "current" marker sits two tabs to the
  right on every phone screen because the sliding indicator (Batch 164) is `absolute top-0`
  with no `left-0` (`TabBar.tsx:173`; check `ui/tabs.tsx`, which uses the same hook). "Football
  Stats" wraps and squashes its icon to 20×8 at 390. Home's stat labels cut off ("PICKS …",
  "WIN RA…") at 390 and the standings `<h1>` at 320. At 200% zoom on a 1280 viewport the header
  overflows by 79 px and pushes the account menu off-screen (Batch 168).

  Anchor the indicator; label the tab "Football" with a fixed 20×20 icon; let the stat labels
  read "Points / Won / Win %" or wrap; let the zoomed header wrap or collapse its secondary
  items.

  Verification: indicator x equals the active tab's x on every tab at 390 and 1280; icon box
  20×20; no clipped text at 320 and 390 under the text-spacing override; at 1280 @ 200% the
  account menu is reachable and the header does not overflow.

  Scope boundary: the tab bar, home's stat labels, the header at zoom. **Web-only.**

- [ ] **Batch 171 — Every translucent colour in the app compiles to nothing, so the header and tab bar have no fill**
  — specified from `docs/review/2026-09-28/06-premium-design.md`, DES-11 (high impact, live,
  verified against production's stylesheet). The Tailwind colours are `var(--…)` hex tokens
  with no `<alpha-value>`, so all **53 opacity-modified utilities (126 uses in 40 files)** —
  `bg-primary/15`, `border-error/40`, `bg-surface/95` … — are silently dropped: none is in the
  built CSS (checked against production's `index-*.css`). The header and tab bar are
  transparent, error panels have no tint, and Batch 138's contrast reasoning assumed chips
  whose tint never rendered. Switching them on as written would fail AA in 13 places.

  First give `TopBar.tsx:110` and `TabBar.tsx:157` a solid `bg-surface`. Then add RGB channel
  tokens beside each hex in `index.css` and `rgb(var(--x-rgb) / <alpha-value>)` colours in
  `tailwind.config.ts`, and in the same batch rewrite the 126 uses to the AA-safe caps in 06's
  top-ten #3 (text on a tint is `--text-primary`; ink moves to border/icon; tint `/8` light,
  `/15` dark; chrome `/95`). Add a check that fails when a utility in `src` produces no CSS
  (a vitest over the built stylesheet is enough — no protected file needed).

  Verification: every opacity utility present in the built CSS; axe `color-contrast` clean in
  both themes at both widths on every route; rendered contrast of the 13 pairs 06 lists;
  before/after captures of the header over scrolled content.

  Scope boundary: colour tokens and their utilities. No layout change. **Web-only.**

- [ ] **Batch 172 — Offline, loading and failure states that tell members the wrong thing**
  — specified from `docs/review/2026-09-28/03-ux-accessibility.md` UX-31 and UX-25 (MED, live,
  verified) and `06-premium-design.md` DES-17 (med); DES-16 is UX-31. **Offline:** with the app
  open and the connection gone, tapping a pick gives an endless spinner, every selection
  disabled, no message and zero requests — TanStack Query's default `networkMode: 'online'`
  pauses the mutation, so Batch 90's offline branch in `usePickEditor.ts` never runs. The pick
  lands on reconnect, but the member is never told it is queued. **Failure as empty:** six
  screens render a 500 as empty, blank or loading — the coupon shows "No coupon this week yet"
  with the raw text "Internal Server Error" (`CurrentRoundPage.tsx:459-467`), My Leagues and
  league members show nothing, league activity and site-admin players look empty, the admin
  dashboard's skeletons never resolve. **Loading as first run:** home tells a member who has
  leagues "together when your first league begins" while it loads or fails
  (`DashboardPage.tsx:334`).

  Set `networkMode: 'always'` on the pick mutation (or route the offline case explicitly) so
  the queued message shows; use `QueryErrorState` with a retry on the round page first, then
  the other five; give home a neutral subtitle until the summary resolves.

  Verification: Chromium offline mid-session → tap → "queued" message, then reconnect → one
  POST, the Batch 90 lost-race message still correct; each of the six screens with its main
  request forced to 500 shows an error with a working retry, distinct from its true empty
  state (hash-compared); home's loading capture shows no first-run copy.

  Scope boundary: these states. No data-layer redesign. **Web-only.**

- [ ] **Batch 173 — A settled round still reads as a price board, and its losers are dimmed below AA**
  — specified from `docs/review/2026-09-28/06-premium-design.md` DES-15 and DES-20,
  `03-ux-accessibility.md` UX-18 (MED, carried from 2026-09-13 and never batched) and UX-21
  (MED), and `02-correctness.md` CORR-26 (LOW). A lost pick is `opacity-60` on the settled
  coupon (`PickRow.tsx:238`, 2.39-3.24:1) and on the player profile
  (`PlayerProfilePage.tsx:160`, 2.24-2.8:1). A lost coupon's headline is the price, the slate
  still shows potential points on lost and void picks, and the header reads "4 of 3" once a
  member who picked has left or been erased (`CouponSection.tsx:130` counts today's roster). An
  erased member appears as "Former" — "taken by Former" — because first-word shortening is
  applied to "Former member". And a member whose only settled picks were void has a `null` win
  rate (Batch 131), which `PlayerProfilePage.tsx:98-101` explains as "Nothing has settled yet" —
  false for them; Batch 131's session log named it and left it (07, PIPE-15).

  Remove the opacity and mark state with ink and text instead; headline a settled coupon with
  its result ("Coupon lost · 3 of 8 landed") and strike the price; mark settled selections
  "Won · N pts" / "Lost" / "Void" with no potential points; head a settled coupon with its leg
  count, not today's roster; never shorten "Former member"; say "Only void picks so far — no win rate yet" when that is
  the case. Values: 06 top-ten #7, mockup
  `mockups/settled.html`.

  Verification: axe `color-contrast` clean on the settled coupon and profile in both themes;
  a settled coupon with a void leg, a departed member and an erased member captured at 390
  and 1280 reading correctly; the share text unchanged except where it read "N of M".

  Scope boundary: the settled presentation. No scoring change. **Web-only.**

- [ ] **Batch 174 — Keyboard focus hides behind the chrome and falls to the top of the page**
  — specified from `docs/review/2026-09-28/03-ux-accessibility.md`, UX-28, UX-30, UX-22 (MED)
  and UX-29, UX-33, UX-23 (LOW), all live and verified. Focus lands behind the tab bar and the
  sticky header, so on a phone the focused selection buttons are fully hidden (WCAG 2.2
  2.4.11). Escape on five dialogs (leave league ×3, delete league, delete player) drops focus
  to `<body>`. The phone install gate is outside any landmark and every Tab stop is on the
  sign-in form hidden behind it. The focus ring is never drawn on "How scoring works" and is
  clipped in horizontal scroll strips. Claiming a pick drops focus to the page body. The two
  profile pages have no `<h1>` while loading or failed.

  `scroll-padding` for the sticky chrome; return focus to the trigger on every dialog, copying
  the More sheet (Batch 167); make the install gate a landmark and `inert` the form behind it;
  draw the ring on those controls and inset it in scroll strips; keep focus on the claimed
  selection; a stable `<h1>` on both profiles in every state.

  Verification: a keyboard walk sign-in → pick at 390 and 1280 with every focused element
  fully visible (bounding box not under the chrome); Escape on each of the five dialogs returns
  focus to its trigger; axe `landmark-one-main`/`region` clean on the install gate; keystroke
  count recorded (32 today).

  Scope boundary: focus management and landmarks. **Web-only.**

- [ ] **Batch 175 — The pick screen hides the prices below the fold and sets them at caption size**
  — specified from `docs/review/2026-09-28/06-premium-design.md`, DES-13 (high) and DES-14
  (med); closes the rest of 2026-09-13 DES-02. Every league screen spends most of the first
  phone screen on navigation — breadcrumb, league switch strip, sub-nav pills — so on the round
  the first price sits at y=1134 against a visible 783. The price, the number the game is
  about, is 12 px like the small print around it.

  Replace the breadcrumb, `LeagueSwitchStrip` card and `CouponSubNav` row on the round with one
  48 px context row; on phones move the coupon accordion below the slate; `TopBar` 52 px and
  drop the extra `+1rem` at `TopBar.tsx:111`. In `PickCard.tsx` `SelectionButton`: label
  `text-label` (14/18), price `text-price` (17/20, 600, tabular), one caption meta line,
  `min-h-[56px]`; add both sizes to `tailwind.config.ts`. Values and contrast: 06 top-ten #4
  and #5; mockup `mockups/round.html`.

  Verification: first price ≤480 px from the top at 390 in both themes; at 1280 the slate and
  the status/coupon column side by side; target sizes ≥24 px (44 px on the selection buttons);
  axe clean; layout shift on load re-measured (0.247 today).

  Scope boundary: the round screen's chrome and selection button. Other league screens adopt
  the context row in a follow-up. **Web-only.**

- [ ] **Batch 176 — At desktop width a ranking reads in Z order**
  — specified from `docs/review/2026-09-28/06-premium-design.md`, DES-12 (med, live). Batch
  140 made standings and results two-column grids at 1280, so rank 1 sits beside rank 2 and a
  ranking reads left-right-left.

  One column at every width: 52 px rows at 390 (rank · name + form · points 17/600), columns for
  played / won / average odds at 1280, a 3 px medal bar on ranks 1-3, the member's own row
  tinted. Same rule for results. Values: 06 top-ten #6; mockup `mockups/standings.html`.

  Verification: captures at 390 and 1280 in both themes; axe clean; the season selector and
  the Batch 165 query keys unchanged.

  Scope boundary: the standings and results layouts. **Web-only — needs Batch 171's tint
  tokens for the own-row tint.**

- [ ] **Batch 177 — Small consistency and web-performance residue**
  — specified from `docs/review/2026-09-28/06-premium-design.md` DES-08 (residue), DES-19,
  DES-21, DES-22 (low) and `04-performance-operations.md` PERF-16 (partial) and PERF-17 (not
  fixed). Home draws the statistic figure white where profiles draw it green; Football Stats
  opens with every table collapsed; the offline banner is off-palette and scrolls away;
  site-admin tab labels overlap at 390; 42 query keys remain inline outside the Batch 165
  factory; `/login` still downloads three font files (48.8 KiB, one preloaded).

  Drop home's colour override; open the first football table; a sticky, token-based offline
  banner; a scrolling admin tab strip; move the remaining keys into `queryKeys`; load only the
  sign-in screen's one face up front.

  Verification: captures of each; no inline `queryKey: [` left in `src`; cold `/login` font
  bytes measured before and after.

  Scope boundary: these six. **Web-only.**

- [ ] **Batch 178 — The installed app does not look like the app**
  — specified from `docs/review/2026-09-28/06-premium-design.md`, DES-18 (med; files and
  geometry verified, on-device rendering plausible — no WebKit here). The manifest and splash
  are navy `#071A3D` with paper and gold while the app is near-black with emerald; the
  "maskable" icon is identical to the plain one, so launchers crop it; `theme-color` is one
  value for both schemes; installed mode shows a 140 px header; `vite.config.ts` still lists
  the font Batch 164 deleted.

  Owner decision first (brand colour, 06 decision 1). Then: manifest `theme_color` /
  `background_color`, `id: '/'`, screenshots; two `theme-color` metas by colour scheme kept in
  step by `ThemeContext`; a real maskable icon (content inside the safe circle) from
  `generate-icons.mjs`; `apple-mobile-web-app-status-bar-style` `default`; remove the stale
  font entry.

  Verification: the maskable icon rendered inside circle and squircle masks; manifest
  validated; standalone captures with a real safe-area inset in both themes.

  Scope boundary: the PWA shell. **Web-only — waits on the owner's brand-colour decision.**

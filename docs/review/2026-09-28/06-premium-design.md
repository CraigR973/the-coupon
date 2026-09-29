# 06 — Premium design

Judgement, but concrete. The bar is the finish of FotMob, Sleeper, the official FPL app and
Apple Sports, **within the owner's text-only decision** (no crests, badges or imagery — not
reopened here). Working notes, scripts and raw output: `notes/06-design/` (`progress.md` says
where the pass is).

## Method

- **Stack.** The production bundle built by `notes/06-design/build_web.py` (cwd `apps/web`, CSS
  45,794 B — the same file, `index-Br02Ny1y.css`, that production serves) on `127.0.0.1:4360`,
  against a lens-06 copy of the harness stack on `127.0.0.1:8160`
  (`notes/06-design/stack_design.py`). That stack serves the e2e server unchanged plus one
  test-only endpoint, `POST /__review/move-price` (`notes/06-design/review_server.py`), which
  moves a price on the running FakeBetfair so that "price moved" could be driven for real.
  `ODDS_PROVIDER=fake`, scheduler off, scratch PostgreSQL, migration 026.
- **Data.** Lens 03's seed plus five more members in `the-coupon` (8 in all), so standings and the
  shared pick budget behave like a real league (`seed_design.py`). A genuinely settled round was
  produced in process with the app's own `settle_gameweek_via_provider` after real picks, a real
  account deletion and a real lock: 3 won, 1 void, 4 lost (`settle_design.py`, `settle-output.txt`).
- **Browser.** Playwright Chromium 148, Node 24, deviceScaleFactor 1, service workers blocked,
  390×844 and 1280×800, both themes. Standalone mode was emulated the way the app detects it
  (`navigator.standalone` and a `display-mode: standalone` matchMedia shim) with **real**
  `env(safe-area-inset-*)` values set through CDP `Emulation.setSafeAreaInsetsOverride`
  (59 px top for a Dynamic Island, 34 px bottom), iOS user agent, touch (`pwa.mjs`).
- **Corpus.** 99 new captures, all listed with the evidence for their state in
  `screenshots/INDEX.md` (lens 06 section). Every state was driven, none mocked, and each row
  states what proved it (the HTTP status the page received, or its text) — never the file name.
  Hashes: 99 distinct, no duplicates (`notes/06-design/duplicates.txt`). The PNGs I viewed by eye
  — 23 of mine and 29 of lens 03's — are listed in `notes/06-design/opened.txt`.
- **Measurements.** First-content position and a rendered type census on the core screens
  (`measure.mjs` → `measure-open.txt`), layout shift with every API read held 1.2 s
  (`cls.mjs` → `cls.txt`), the tab-bar indicator with motion on and off (`tabbar-probe.txt`),
  which opacity-modified utilities exist in the built CSS (`opacity-modifier-audit.txt`), icon
  pixels and launcher masks (`pwa/icon-masks.html` → `.png`), and the contrast of every colour
  proposed below (`contrast.py` → `contrast.txt`, 110 pairs).
- **Production** was touched once, read-only: `GET /` and its stylesheet, to confirm the live CSS
  is the same file and carries the rule behind DES-10.

**A corpus defect, found by opening captures.** 26 of lens 03's captures whose state is not
"offline" show the amber offline banner (`navigator.onLine` was false in that run), and at least
two are empty: `my-leagues--happy--390--dark.png` shows no leagues and
`league-members--happy--390--light.png` shows only the heading. The scan is
`notes/06-design/corpus-offline-banner-scan.txt`. I re-captured the affected screens as
`*-l06--*` (my-leagues, discover, join-by-code, create-league, league members, league settings)
and judged from those. Lens 03's other captures that I relied on were opened and are sound.

## Prior findings

Each was re-driven against the stack above — screenshots taken and opened, the geometry measured
— and checked against its batch row's acceptance.

| id | batch | verdict | evidence |
| --- | --- | --- | --- |
| DES-01 desktop is the phone layout stretched | 140 | **partial** | The shell widened (`max-w-7xl`) and the round has two columns — but the left column is a 44 px collapsed "The Coupon" header over empty space for the whole scroll (`current-round--open--1280--dark.png`, `current-round--feedback-queued-offline--1280--light.png`). Standings and results became a two-column **card grid** that reads in Z order (DES-12). Home, the landing screen, is still one 1232 px column with its content in the left third (`home--happy--1280--dark--full.png`, `home--firstrun-l06--1280--dark.png`) |
| DES-02 pick screen opens closed | 139 | **partial** | The first competition now opens (verified, `current-round--open--390--dark--full.png`). The member still arrives at no price: the first price button's top is at **y=1134 against a usable bottom of 783** at 390, and **y=856 against 800** at 1280 (`measure-open.txt`, Alice, two leagues). The cause is DES-13 |
| DES-03 one red toast for every outcome | 139 | **partial** | The variants exist and fire correctly for real: success; warning + "Refresh the card" (lost claim, 409 `SELECTION_TAKEN`); warning + "Take 4.60" (409 `PRICE_MOVED:4.60`); error for `PICKS_BUSY` (429) — `current-round--feedback-*`. But in dark mode every one of them is illegible (DES-10), and the queued-offline message never appears (DES-16) |
| DES-04 toasts under the tab bar / safe area | 149 | **held** | 15 px clear of the tab bar in all 20 phone-width feedback captures, and 15 px clear in standalone with a real 34 px bottom inset (`standings-toast--standalone-safearea--393--*.png`, `pwa-results.json`) |
| DES-05 generic skeletons, content jump | 149 | **partial** | `ui/skeleton.tsx` now uses the shimmer; home, football and profile resolve with **CLS 0**. The round still jumps **0.247** at 390 (0.041 at 1280) and standings **0.141** (0.058) — `cls.txt`, every read held 1.2 s |
| DES-06 error looks like empty, no retry | 149 | **partial** | Home, results, standings, football, team season and career profile have a distinct error with "Try again" (`home--error--390--dark.png`). Six screens still show a failure as empty, blank or loading, the coupon among them — lens 03's UX-25 |
| DES-07 first-run home stops at 58% | 150 | **held** | Fills the fold at 390 with a button-weight "Find a league" and a secondary "Join by code" (`home--firstrun--390--dark.png`, `home--firstrun-l06--390--dark--full.png`). At 1280 the hero is the stretched 1232 px card (DES-01) |
| DES-08 one statistic drawn five ways | 151 | **partial** | One `StatCard` now serves home and both profiles. Home still overrides the figure to white while the profiles draw it emerald (`DashboardPage.tsx:385-406` `valueClassName="text-text-primary"` vs `StatCard.tsx` default `text-primary`), and home's labels truncate at 390 — "PICKS …", "WIN RA…" (`home--after-settle-loser--390--light.png`; lens 03 UX-15) |
| DES-09 no type scale; 84 nodes ≤11 px | 151 | **held** (floor) | **0** text nodes under 12 px on home, round, standings and results at both widths (was 84) — `measure-open.txt`. The "scale" is one token (`fontSize.caption`) over Tailwind's defaults, and the floor is now where most text lives: 52 of 74 text nodes on the round are 12 px (DES-14) |
| Focus ring (UX-14) as a visual element | 158 | **held** | The two-ring token (2 px surface gap + 3 px ink) reads as a designed ring, not a browser default, and inherits the ink's 4.5:1. Two clipped instances and focus hidden under the sticky chrome are lens 03's UX-28/UX-29 |
| Targets and zoom chrome (UX-19/20) | 168 | see lens 03 | Measured there (UX-20 partial, UX-27). Visually the two links now read as tappable rows on login and settings |

**Tally: 3 held, 6 partial, 0 regressed, 0 not fixed** (DES-01..09), plus the focus ring held.
One thing did regress under a batch: Batch 149's final commit (`4121cf0`) is what made dark-mode
toasts illegible — recorded as a new finding (DES-10) because it is a different defect from DES-04.

## Register

| id | impact | live | verified | finding |
| --- | --- | --- | --- | --- |
| DES-10 | **high** | live | verified | Every toast is illegible in dark mode — title contrast 1.01–1.07:1 |
| DES-11 | **high** | live | verified | The tint layer does not exist: 53 opacity-modified token utilities (126 uses, 40 files) compile to nothing — the header and tab bar have no fill |
| DES-13 | **high** | live | verified | Every league screen spends most of the first phone screen on navigation; the first price is 351 px below the fold |
| DES-12 | med | live | verified | At 1280 the standings and results lists are two-column grids, so a ranking reads in Z order |
| DES-14 | med | live | verified | The price — the number the game is about — is set at caption size |
| DES-15 | med | live | verified | A settled round still reads as a price board, and a lost coupon's headline is the price, not the result |
| DES-16 | med | live | verified | The queued-offline reassurance never appears when the connection drops mid-session — the member gets a spinner |
| DES-17 | med | live | verified | Home tells a member with leagues "together when your first league begins" while it loads and when it fails |
| DES-18 | med | live | plausible (Android/iOS rendering) / verified (files, geometry) | The installed-app shell does not match the app: navy splash and status bar, a non-maskable "maskable" icon, a 140 px standalone header |
| DES-19 | low | live | verified | Football Stats opens with every table collapsed |
| DES-20 | low | live | verified | An erased member is shown as "Former" — "taken by Former", "Picked by Former" |
| DES-21 | low | live | verified | The offline banner is off-palette and scrolls away |
| DES-22 | low | live | verified | Site-admin tab labels overlap at 390 |
| DES-23 | low | live | verified | An invite link lands on "Join the league" without naming the league or the inviter |

Cross-lens items rated here by design impact but owned elsewhere (not re-numbered): the tab bar's
marker two tabs to the right and the wrapped "Football Stats" label with its 20×8 icon are lens
03's **UX-26** and **UX-24** — re-measured with motion on and off (`tabbar-probe.txt`: offset
exactly 156 px on every route, both settings), and on every phone screen they are the most-seen
defect in the product, so they are in the top ten below. The settled coupon's "8 of 7" header and
the results list multiplying void legs in (2186.89 on the list, 1214.94 on the coupon) are lens
02's CORR-26 and CORR-21, reproduced here on the settled round
(`coupon--settled-void--390--dark--full.png`, `results--settled--390--dark.png`).

### DES-10 · high · live · verified — every toast is illegible in dark mode

`AppToaster` renders Sonner with `richColors` and no `theme`, so Sonner uses its **light**
palette in both app themes (pale mint, cream and pink backgrounds). Batch 149's final commit
(`4121cf0`, 28 Sep) added `.coupon-toaster [data-rich-colors='true'][data-sonner-toast]
[data-title] { color: var(--text-primary) !important }` (`index.css:430-434`) to fix light-mode
contrast. In dark mode `--text-primary` is `#F0F4FF`, so the title becomes near-white on a
near-white toast.

Measured from computed styles on real toasts (`feedback-run-1.txt`, `feedback-run-2.txt`,
`busy-run.txt`):

| toast | dark | light |
| --- | --- | --- |
| success "Grabbed … @ …" | **1.04:1** | 16.87:1 |
| warning — lost claim, price moved | **1.07:1** | 17.31:1 |
| error — `PICKS_BUSY` | **1.01:1** | 16.08:1 |

Evidence: `current-round--feedback-conflict--390--dark.png`,
`current-round--feedback-price-moved--1280--dark.png`, `current-round--feedback-busy--390--dark.png`.
Dark is the default theme for a first-time visitor (`index.html` pre-mount script).

Tried to disprove: the production stylesheet is the same file (`index-Br02Ny1y.css`) and carries
the rule (`GET https://the-coupon-production.vercel.app/assets/index-Br02Ny1y.css`); Sonner's
default `theme` is `light` regardless of `prefers-color-scheme`; the context's colour scheme was
dark in every dark run. The light-mode values show the override does its job there.

**Member impact:** in the default theme, a member who loses a claim, whose price moved, or whose
league is busy is shown a pale box they cannot read — at the one moment the app needs them to act.

**Fix:** pass `theme` from `ThemeContext` to `<Toaster>` and replace `richColors` with app-owned
toast classes on tokens: `--surface-overlay` fill, a 3 px left edge and icon in the semantic
`-ink`, title `--text-primary`, body `--text-secondary`, the action as a `--primary` button
(top-ten #1, mockup `mockups/toasts.html`). Add a dark-mode toast to the prod-bundle smoke with a
colour-contrast assertion. Web-only, XS.

### DES-11 · high · live · verified — the tint layer does not exist

Every colour token is a bare `var(--x)` hex in `tailwind.config.ts`, which Tailwind 3 cannot
apply an alpha to, so **every** opacity-modified token utility compiles to nothing. The audit
(`opacity-modifier-audit.txt`) found 53 distinct classes, 126 uses in 40 files, **0** present in
the built CSS: `bg-primary/15` (11 uses — the active pill in every sub-nav), `bg-error/10` and
`border-error/40` (error panels), `bg-success/20` (the picked selection), `border-border/50`,
`bg-surface/90` and `bg-surface/95` (the sticky header and the tab bar), and 46 more. The header's
computed background is `rgba(0, 0, 0, 0)` (`pwa-results.json`); in every phone capture the tab
bar shows blurred page content through its labels (`standings-toast--standalone-safearea--393--light.png`,
`home--firstrun--390--dark.png`). It has been this way since the first commit (`46caf87`, the
calcio clone), so it is latent rather than a regression.

**The naive fix would regress AA.** Turning the tints on at their authored alphas fails 4.5:1 in
13 pairings, mostly light mode, because the light `-ink` colours already sit at the limit on
`--surface-elevated` (`contrast.txt`): e.g. `--primary-ink` on `bg-primary/15` over
`--surface-elevated`, light, **3.80:1**; `--success-ink` on the picked button's `bg-success/20`,
light, **3.57:1**; `--error-ink` on `bg-error/10` over `--surface-elevated`, light, **3.90:1**.
The largest alpha that keeps ink text at 4.5:1 on `--surface-elevated` in light mode is **0–1%**
for primary, success, error and warning.

**Member impact:** the chrome the member touches on every screen has no fill, so tab labels sit
on whatever scrolls behind them, and the selected/at-risk/error states the design intended are
flat outlines — the product looks less finished than its own source.

**Fix:** (1) header and tab bar solid `bg-surface` now (no config change), or `/95` once alpha
works — at 95% the active tab ink clears 4.52:1 in light over the worst content behind it, at 90%
it does not (4.10); (2) give the tokens alpha support (`rgb(var(--x-rgb) / <alpha-value>)`), and
in the same batch rewrite every tinted pairing so text on a tint is `--text-primary` and the ink
colour moves to the border or icon (all such pairings pass, `contrast.txt` group 2), with tints
capped at 8% light / 15% dark; (3) a gate check that fails when a class used in `src/` is missing
from the built CSS, so a dead utility cannot ship again. Web-only, S–M. Top-ten #3.

### DES-13 · high · live · verified — navigation before content on every league screen

At 390 the round page stacks the header (80 px), a tracked breadcrumb that wraps to two lines
("… · GAMEWEEK / 1B"), the h1, a "Your leagues · tap to switch" card (90 px), a "Current round /
Season" pill row, a gameweek navigator, a status card, the coupon accordion, "Pick your
selection", "How scoring works" and the competition header — **19 tracked uppercase labels** —
before the first price, whose top is at **y=1134** with the usable screen ending at 783
(`measure-open.txt`, `current-round--open--390--dark--full.png`). At 1280 the first price is at
y=856 (fold 800). Standings repeat the pattern — league card, season card, copy button, two
explanatory paragraphs — so the table starts at about y=515 and **2.7 of 8 rows** are visible
(`standings--settled-8-members--390--dark--full.png`). In standalone mode the header alone is 140 px
(59 inset + 16 + 64) and the tab bar 95 px, leaving 617 px of 852 (`pwa-results.json`).

The same count appears four ways on one screen: "0 picks" (navigator), "0 of 3 picked" and
"3 to go" (status card), "0 of 3" (coupon header).

Tried to disprove: measured as Alice (two leagues) — a one-league member is spared the switcher
card (`current-round--feedback-price-moved--1280--dark.png`, Hana), but still has 650+ px of
chrome at 390.

**Member impact:** the member opens the app to pick and sees no price without scrolling, every
week; FotMob, Sleeper and FPL all put the list under the header.

**Fix:** one compact context row replaces the breadcrumb, the switcher card and the pill row (league
name as a menu button, gameweek and status on the right); the count shown once; the coupon
accordion moved below the slate on phones; header row 52 px and the extra 16 px top pad dropped
(`TopBar.tsx:111`). Target: first price ≤ 480 px at 390. Top-ten #5, mockup `mockups/round.html`.
Web-only, M.

### DES-12 · med · live · verified — two-column lists read in Z order at 1280

Batch 140 made the standings and results lists `grid-cols-2` at the large breakpoint. A ranking
split into two columns reads 1 | 2, 3 | 4, …: with 8 members the eye zig-zags and tied ranks
straddle the columns (`standings--settled-8-members--1280--dark.png`: "4 Bob | 4 Former member,
4 Ivan | 4 Jo …"). The results list does the same with gameweeks, newest first
(`results--archive-season--1280--dark.png`).

**Member impact:** on a laptop — a supported way to play — the league table is harder to read
than on the phone.

**Fix:** a single-column table at every width; at 1280 add columns (played, won, avg odds, form,
points) instead of a second column of cards, and put the member's form or the round summary in a
side column. Medal bar on ranks 1–3 (`--gold`/`--silver`/`--bronze`, 3.1–10.6:1 as non-text). Top-ten
#6, mockup `mockups/standings.html`. Web-only, S.

### DES-14 · med · live · verified — the price is set at caption size

On the pick button the label, the price and the "WIN 19 PTS" line are all 12 px
(`PickCard.tsx:353-367`, `text-xs` and `text-caption`); the price is `font-mono text-xs`. On the
round, 52 of 74 visible text nodes are 12 px (`measure-open.txt`). Batch 151 raised the floor, but
most of the screen now sits on it, so nothing leads: a price looks like metadata.

**Member impact:** comparing prices — the whole decision — means reading the smallest type on the
screen.

**Fix:** price 17 px/600 tabular mono in `--text-primary`, label 14 px, one meta line at 12 px; a
56 px minimum button. Adds two scale steps (`fontSize.price: 17px/20px`, `fontSize.label:
14px/18px`). Sizes only, so contrast is unchanged (16.3:1 / 17.8:1 on `--surface`). Top-ten #4,
mockup `mockups/round.html`. Web-only, S.

### DES-15 · med · live · verified — the settled state reads as a price board

After settlement the slate is unchanged: the lost Chelsea button still says "taken by Jo · 43 pts",
the void BTTS button "taken by Ivan · 18 pts" — the points they would have won, on selections that
lost or never ran (`current-round--settled-winner--1280--light--full.png`). There is no score for
any fixture. The coupon card leads with **1214.94** at 30 px in white, with the outcome in a 12 px
grey chip "Not all legs landed" (`coupon--settled-void--390--dark--full.png`). The legs list itself
is good — won/lost/void chips, the member's own leg outlined, "1 leg voided — not in the combined
price" — so Batch 156 reads correctly.

**Member impact:** on Saturday evening the member has to open the legs list to learn whether the
coupon won, and the slate still advertises points nobody scored.

**Fix:** the headline is the result — "Coupon lost · 3 of 8 landed" in `--error-ink` at 24 px
(5.62:1 dark / 5.02:1 light), the price struck through in `--text-secondary`; "Coupon won" in
`--success-ink`. Settled selection buttons show "Won 19 pts" / "Lost" / "Void" and drop potential
points. Top-ten #7, mockup `mockups/settled.html`. Web-only, S.

### DES-16 · med · live · verified — queued-offline shows nothing

Driven four times: the page loaded, the context went offline, the member tapped a selection. No
toast, no outstanding-pick notice, no POST — only a spinner in the button — after 5 s
(`current-round--feedback-queued-offline--*.png`). Reconnecting sent the pick (201) and showed
"Grabbed … @ …" (`current-round--feedback-queued-reconnected--*.png`). Cause (plausible, from the
source): React Query's default `networkMode: 'online'` pauses the mutation while offline, so
`mutationFn` never runs and `usePickEditor`'s `NetworkError` branch — the info toast and the held
"queued" state — is unreachable in this path. It can only fire when the app was opened offline.
The offline banner, meanwhile, sits in the page flow and has scrolled away by the time the member
reaches a price (DES-21).

**Member impact:** in a stadium or on a train, a member taps a selection and watches a spinner with
no explanation; many will tap another, which then silently replaces the first on reconnect.

**Fix:** `networkMode: 'always'` on the pick mutation so the existing queued path runs, and a
test that goes offline *after* load. Web-only, XS. (Owned here because it defeats a Batch 139
acceptance item; lens 02/03 may want it too.)

### DES-17 · med · live · verified — home shows first-run copy to every member while loading

The hero's subtitle is the no-league sentence until the summary arrives: Alice, a member of two
leagues, sees "Your picks, deadlines and results — together when your first league begins." in the
loading and the error states (`home--loading--390--light.png`, `home--error--390--dark.png`).

**Member impact:** on a slow connection every returning member is briefly told they are in no
league; on a failure they are told it indefinitely.

**Fix:** a neutral subtitle (or a skeleton line) until the summary resolves; first-run copy only
when `leagueCount === 0` is known. Web-only, XS.

### DES-18 · med · live · verified (files, geometry) / plausible (on-device rendering) — the installed shell does not match the app

- **Colour.** The manifest's `theme_color` and `background_color` and the dark `theme-color` meta
  are navy `#071A3D` (`vite.config.ts`, `ThemeContext.tsx:33`), a colour the app's interface never
  uses. The Android splash is navy, the app's first paint `#0B0E13` (dark) or `#F7F8FA` (light), and
  the standalone status bar is a navy band above a `#131720` header (`pwa/icon-masks.png`, sections
  3–4).
- **Maskable icon.** `icon-maskable-512.png` is byte-identical to `icon-512.png` (`cmp`), i.e. the
  "any" icon with transparent 96 px corners; the ticket's notched ends sit outside the 80% safe
  circle (`pwa/icon-masks.png`, section 1). The icon is navy/paper/gold; the app's mark is an
  emerald outline ticket with a brass wordmark — two brands.
- **iOS.** `apple-mobile-web-app-status-bar-style` is `black-translucent`, which draws white status
  glyphs over the page; in the light theme that is white on `#F7F8FA` (plausible — WebKit cannot run
  here). No `apple-touch-startup-image`.
- **Chrome in standalone.** Header 140 px, tab bar 95 px with real insets (`pwa-results.json`); the
  header content does clear the Dynamic Island (row starts at 75 px) and the toast clears the home
  indicator — those hold.
- The manifest has no `id`, `screenshots` or `shortcuts`, so Android and desktop Chrome show the
  minimal install sheet; `includeAssets` still lists the deleted `jetbrains-mono-700.woff2`.

**Member impact:** the first thing a member sees of the installed app — icon, splash, status bar —
belongs to a different colour scheme from the app that then opens.

**Fix:** top-ten #10. Web-only, S.

### DES-19 · low · live · verified — Football Stats opens with every table collapsed

Both competitions are closed headings with counts (`football--happy--390--dark.png`) — the pattern
Batch 139 fixed on the round. **Fix:** open the first table (or the competition of the member's
next fixture). Web-only, XS.

### DES-20 · low · live · verified — "Former" as a name

`PickCard.tsx:34-35` shortens every name to its first word, so an erased member's "Former member"
becomes "taken by Former" and "Picked by Former"
(`current-round--settled-winner--390--dark--full.png`). The coupon legs and standings say "Former
member" correctly. **Fix:** skip the shortening for the anonymised name (the API could send a flag).
Web-only, XS.

### DES-21 · low · live · verified — the offline banner is off-palette and scrolls away

`OfflineBanner.tsx:13` uses Tailwind's raw amber (`bg-amber-900/80`, `text-amber-100`) in both
themes and sits in the page flow: scrolled to the slate, its top is at y=−760
(`current-round-offline-scrolled--standalone-safearea--393--*.png`). **Fix:** sticky under the header,
on tokens (`--text-primary` on `--warning` at 12% over `--bg`: 14.8:1 dark / 14.8:1 light; icon in
`--warning-ink` 7.6:1 / 4.2:1). Web-only, XS.

### DES-22 · low · live · verified — site-admin tab labels overlap at 390

"Dashboard" and "Calendar" print over each other and "All leagues" is clipped
(`admin-players--happy--390--light.png`). Owner-only screens. **Fix:** a horizontally scrolling
strip with `shrink-0` items. Web-only, XS.

### DES-23 · low · live · verified — the invite landing is anonymous

`/join/:token` shows "Join the league — Create an account or sign in, and this invite will be ready
to claim" with no league name, inviter or member count (`join--happy--390--light.png`; `JoinPage.tsx`
fetches nothing). For most new members this is the first screen. **Fix:** a public invite preview
(league name, inviter's display name, member count) — **API-carrying**, and a privacy decision for
the owner (see below).

## Per screen

What works (do not churn it) and what breaks the premium feel. Paths are under `screenshots/`.

**The system underneath.** Still genuinely good: the brass mono wordmark and emerald ticket, the
card system, the two considered palettes, tabular mono numerals, the ink/fill split in
`index.css`, the two-ring focus token. What breaks it across the board is DES-11 (no fills, no
tints), DES-10 (toasts), and the tab bar (UX-24/26).

| screen | works | breaks |
| --- | --- | --- |
| Home, populated | hero with greeting and "1 league needs a pick → locks in 2d 20h"; per-league cards with status chip, pick, fold, standing (`home--happy--1280--dark--full.png`) | stretched at 1280 (DES-01); stat labels truncate at 390, figure white here and emerald on profiles (DES-08); first-run copy while loading (DES-17) |
| Home, first run | real primary + secondary action, three numbered steps (`home--firstrun-l06--390--dark--full.png`) | hero stretched at 1280 |
| Round, open | first group open; clear status card; form letters beside teams; "your game" and "taken by" states (`current-round--open--390--dark--full.png`) | price below the fold (DES-13); price at caption size (DES-14); "English Premier League" chip repeated inside the "English Premier League" group; timestamp in every taken button ("29 Sep, 23:48") |
| Round, feedback | the right variant and action for each refusal, driven for real (`current-round--feedback-*`) | dark toasts illegible (DES-10); queued shows nothing (DES-16); the confirmation toast covers the button it confirms at 390 (`…feedback-confirmed--390--light.png`); toast says "Grabbed Yes" where the button says "Both teams score" |
| Round, locked | "Coupon complete · Picks are locked", your pick, 2-fold 7.14 — calm and complete (`current-round--locked--390--light.png`) | — |
| Round, settled + coupon | legs list with won/lost/void chips and "You" marker; void explained (`coupon--settled-void--390--dark--full.png`) | price as headline, outcome in a grey chip; slate unchanged (DES-15); "8 of 7" (CORR-26); "taken by Former" (DES-20); a 2 px focus frame around the whole coupon when arriving by URL (`coupon--settled-void--1280--dark.png`, programmatic focus matching `:focus-visible`) |
| Results | one row per round with winner, landed count, fold price, coupon chip (`results--settled--390--dark.png`) | Z order at 1280 (DES-12); "22 pts" reads as the member's own; "Gameweek 1b" here, "GAMEWEEK 1B" everywhere else; void legs multiplied (CORR-21) |
| Standings | rank, avatar, name, won, avg odds, form letters with points (`standings--settled-8-members--390--dark--full.png`) | 88 px rows — 2.7 of 8 visible; chrome before the table (DES-13); Z order at 1280 (DES-12); medal tokens exist and are unused |
| Career / player profile | "Your record" header, stat tiles, "what you pick" definitions (`career-profile--settled-l06--390--dark.png`) | third tile orphaned on its own row at 390; lost rows dimmed below AA (UX-21) |
| My leagues | hub cards with privacy chip, members, rank, points (`my-leagues--happy-l06--390--dark.png`) | "League hub" overline repeated on every card; at 1280 two cards in a 1232 px row with the rest empty |
| Discover / join by code / create | plain, consistent forms (`create-league--happy-l06--390--light.png`) | — |
| League admin | settings grouped into cards with good helper copy; invite code as a brass moment (`league-settings--happy--1280--dark--full.png`, `league-invites--happy--390--dark.png`) | one "Save changes" mid-page between independent actions (no sticky save bar); a red "Remove" on every member row at the weight of "Promote" (`league-members--happy-l06--390--dark.png`) |
| Site admin | an honest ops console: stuck rounds, budgets, scheduler (`admin-dashboard--happy--1280--dark.png`) | tab labels overlap at 390 (DES-22); no error states (UX-25) |
| Football | team season is FotMob-grade: date, H/A, score chip, result letter (`team-season--happy--1280--light.png`) | tables collapsed (DES-19); "POSTPONED" in large tracked mono outweighs the team name; the results date strip clips a chip under its arrow (`football--results--390--light.png`) |
| Auth family | centred lockup, 4-box PIN, one primary, honest copy about PIN recovery (`login--happy--390--light.png`, `register--happy--390--dark.png`) | welcome repeats its tagline twice ("One pick. One coupon. Every Saturday." then "One Saturday pick. One shared coupon."); PIN boxes left-aligned with a 100 px gap; invite landing anonymous (DES-23) |
| Install gate | two clear steps with icons (`install-gate--mobile-browser--390--dark.png`) | outside any landmark (UX-22) |
| Settings | consistent cards; segmented odds/appearance controls; data export and deletion clearly separated (`settings--happy--390--light--full.png`) | the disabled "Change PIN" button is pale green **with a tick**, which reads as "done"; "Install App" is a dead end ("Use your browser's install option"); section heading style differs from the round's mono overlines |
| About | the "if your pick wins" odds→points table is the clearest explanation in the app (`about--happy--390--dark.png`) | — |
| PWA shell | toasts and header clear the insets (`standings-toast--standalone-safearea--393--light.png`) | DES-18; tab bar with no fill (DES-11) and a misplaced marker (UX-26) |

## The ten highest-leverage changes

Ranked by impact ÷ effort. Every colour is a token that already exists; every pairing's contrast is
in `notes/06-design/contrast.txt` (both themes, every surface it sits on). The mockups are
self-contained HTML using the app's token values and its own self-hosted fonts, screenshotted at
390 and 1280 in Chromium beside the HTML.

1. **Theme the toasts** (DES-10). `AppToaster.tsx`: `theme={resolvedTheme}`; drop `richColors`;
   `toastOptions.classNames` → `bg-surface-overlay text-text-primary border border-border shadow-lg`
   with `[data-type=success|warning|error|info]` setting a 3 px left border and icon colour from
   `--success-ink` / `--warning-ink` / `--error-ink` / `--primary-ink`; action button `bg-primary
   text-on-primary`. Delete `index.css:428-434`. Contrast: title 13.17:1 dark / 17.79:1 light;
   body 5.65 / 7.56; icon/edge 4.54–6.75 dark, 5.02–5.07 light (3:1 needed); action 7.62 / 5.13.
   Before: `current-round--feedback-conflict--390--dark.png`. Mockup: `mockups/toasts.html`. XS.
2. **Fix the tab bar** (UX-26, UX-24). `TabBar.tsx:173` add `left-0` to the indicator (and check
   `ui/tabs.tsx`, same hook); label "Football" not "Football Stats"; icon `h-5 w-5` not squashed.
   Before: `current-round--open--390--dark.png` (marker over Leagues while Coupon is active). XS.
3. **Give the chrome its fill and make tints real — safely** (DES-11). `TopBar.tsx:110` and
   `TabBar.tsx:157` → solid `bg-surface` now. Then tokens with alpha support in
   `tailwind.config.ts` (`primary: 'rgb(var(--primary-rgb) / <alpha-value>)'`, channels added
   beside each hex in `index.css`), and in the same batch rewrite the 126 uses: text on a tint is
   `--text-primary`; ink moves to border/icon; tint caps `/8` light, `/15` dark. Header/tab bar at
   `/95` (active tab ink 6.28:1 dark / 4.52:1 light over the worst content). Add a dead-utility
   check to the gate. Before: `standings-toast--standalone-safearea--393--light.png`. S–M.
4. **Make the price the hero of the pick button** (DES-14). `PickCard.tsx:327-384` (`SelectionButton`): label
   `text-label` (14/18), price `text-price` (17/20, 600, tabular, `--text-primary`), one meta line
   `text-caption`; `min-h-[56px]`; add `fontSize.price` and `fontSize.label` to
   `tailwind.config.ts`. Taken-by line drops the timestamp. Contrast unchanged (16.30 / 17.79).
   Before: `current-round--open--1280--light--full.png`. Mockup: `mockups/round.html`. S.
5. **Put the first price above the fold** (DES-13, closes DES-02). Replace the breadcrumb,
   `LeagueSwitchStrip` card and `CouponSubNav` pill row on the round with one 48 px context row
   (league name as a menu button · "GW 1b · Open · locks 2d 20h"); show the pick count once; on
   phones move the coupon accordion below the slate; `TopBar` row 52 px and remove the extra
   `+1rem` from `TopBar.tsx:111`. Chips: `--text-secondary` on `--surface-elevated` 6.32 / 6.79,
   active `--on-primary` on `--primary` 7.62 / 5.13. Target first price ≤ 480 px at 390. Before:
   `current-round--open--390--dark--full.png`. Mockup: `mockups/round.html`. M.
6. **Standings as a table** (DES-12, DES-13). `LeaderboardPage.tsx`: single column at every width,
   52 px rows at 390 (rank · name + form · points 17/600), columns for played/won/avg odds at 1280;
   medal bar 3 px on ranks 1–3 (`--gold` 10.62 / 3.24, `--silver` 9.78 / 3.10, `--bronze` 6.10 /
   4.93 as non-text); own row `--primary` at 8% with name in `--primary-ink` (6.32 / 4.57). The
   season and league switchers collapse into the context row. Same single-column rule for results.
   Before: `standings--settled-8-members--1280--dark.png`. Mockup: `mockups/standings.html`. S.
7. **Settled coupon: result first, slate marked** (DES-15). `CouponSection.tsx`: headline "Coupon
   lost · 3 of 8 landed" 24/600 in `--error-ink` (5.62 / 5.02), "Coupon won" in `--success-ink`
   (7.07 / 5.02); price struck in `--text-secondary` (6.99 / 7.56). `PickCard.tsx` settled
   buttons: "Won · 19 pts" `--success-ink`, "Lost" `--error-ink`, "Void" `--text-muted` (all ≥
   4.51 on both surfaces); no potential points after settlement. Before:
   `coupon--settled-void--390--dark--full.png`. Mockup: `mockups/settled.html`. S.
8. **Two honest-state fixes** (DES-16, DES-17). `usePickEditor.ts` mutation `networkMode:
   'always'`; `DashboardPage.tsx` neutral hero subtitle until the summary resolves. Before:
   `current-round--feedback-queued-offline--390--light.png`, `home--loading--390--light.png`. XS.
9. **Small consistency pass** (DES-08, DES-19, DES-20, DES-21, DES-22). Home `StatCard` labels
   "Points / Won / Win %" and drop the white override; open the first football table; no
   first-word shortening for "Former member"; sticky token-based offline banner; scrolling admin
   tab strip. Before: `home--after-settle-loser--390--light.png`, `football--happy--390--dark.png`. XS each.
10. **One brand for the installed app** (DES-18). `vite.config.ts` manifest `theme_color`
    `#131720`, `background_color` `#0B0E13`, `id: '/'`, two `screenshots`; `index.html` two
    `theme-color` metas with `media="(prefers-color-scheme: dark|light)"` — `#131720` / `#FFFFFF`
    (the header surfaces) — and `ThemeContext` writing the same pair; `generate-icons.mjs` a real
    maskable variant (full-bleed plate, ticket ≤ 60% width inside the safe circle) and the plate
    in the app's `--surface`/emerald rather than navy, or navy adopted as a real app token — an
    owner call (below); `apple-mobile-web-app-status-bar-style` `default` so the light theme keeps
    dark status glyphs. Before: `notes/06-design/pwa/icon-masks.png`. S.

None of these reintroduces imagery.

## Checked and found nothing material

- Toast placement against the tab bar and the home indicator, including real safe-area insets
  (DES-04 held).
- Header clearance of a 59 px top inset in standalone; the install gate does not show when the
  app detects standalone.
- The four pick refusals map to the right variant, copy and action; the price-moved action retakes
  the new price (all driven for real).
- Batch 156's void-leg copy on the coupon ("1 leg voided — not in the combined price") and the legs
  list.
- Text below 12 px: none on the core screens at either width.
- The locked round, About, league invites, create-league and settings read cleanly.
- Duplicate captures in lens 06's additions: none (99 distinct hashes).

## Proposed batches

1. **Dark-mode toasts are unreadable** (DES-10) — web-only, XS. Ship first.
2. **The tab bar's marker, label and icon** (UX-26, UX-24) — web-only, XS.
3. **Chrome fill and a real tint layer, AA-safe** (DES-11) — web-only, S–M.
4. **The pick screen: price as hero, first price above the fold** (DES-14, DES-13, closes DES-02) — web-only, M.
5. **Standings and results as single-column tables at every width** (DES-12) — web-only, S.
6. **Settled state: result first, slate marked** (DES-15) — web-only, S.
7. **Queued-offline and home-loading honesty** (DES-16, DES-17) — web-only, XS.
8. **Consistency pass** (DES-08 residue, DES-19, DES-20, DES-21, DES-22) — web-only, XS.
9. **Installed-app shell** (DES-18) — web-only, S; waits on owner decision 1.
10. **Invite preview** (DES-23) — API-carrying (a public read), S; waits on owner decision 2.

## Owner decisions

1. **What colour is the brand?** The icon, splash and status bar are navy `#071A3D` with paper and
   gold; the app is near-black with emerald and brass. Options: (a) move the shell to the app's
   palette (`#0B0E13` plate, emerald ticket) — no new token, consistent at launch; (b) adopt navy as
   a real app token (header/hero) so the shell matches; (c) leave it. **Recommend (a):** the app is
   what members look at for hours; the icon is what they look at for a second.
2. **May an invite link show the league before sign-in?** Options: (a) league name + inviter's
   display name + member count on `/join/:token`; (b) league name only; (c) as now. **Recommend
   (a):** the token is already a secret the inviter chose to share, and a named invite is what makes
   a stranger tap "Create account".

## Doc corrections

- `docs/review/2026-09-28/screenshots/INDEX.md`, lens 03 section — 26 rows whose state is not
  "offline" were captured with `navigator.onLine` false and show the offline banner; at least
  `my-leagues--happy--390--dark.png` and `league-members--happy--390--light.png` show no content.
  From: state "happy"/"firstrun" etc. To: mark those rows "offline banner leaked — see lens 06
  `*-l06--*` re-captures" (list in `notes/06-design/corpus-offline-banner-scan.txt`). For lens 03 or
  the lead to apply.
- `apps/web/vite.config.ts` `includeAssets` lists `fonts/jetbrains-mono-700.woff2`, deleted by Batch
  164 — a code change, so not a doc correction; noted for batch 9.

## What this pass did not do

- **No real device.** WebKit cannot be installed here, so iOS standalone, the `black-translucent`
  status bar and the iOS splash are judged from the spec and the files (marked plausible). Android's
  splash and status bar were not rendered by a launcher; the mask renders are a CSS simulation.
- **No motion review.** All captures used reduced motion; transition timings were not measured
  beyond the tab-bar probe.
- Lens 03's captures of the site-admin sub-screens (calendar, results, sync, invites, all leagues),
  set-PIN, discover and join-by-code were not all opened; the site admin was judged from the
  dashboard and players screens.
- Loading and error states were not re-captured (lens 03's are sound where opened); CLS was
  measured instead.
- The top-ten mockups cover four of the ten; the others are specified by token and file.

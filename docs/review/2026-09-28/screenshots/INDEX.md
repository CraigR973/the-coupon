# Screenshot index — 2026-09-28 review

Each pass appends its own rows.

| file | pass | state shown | how it was driven |
| --- | --- | --- | --- |
| home--last-result-void-unstyled--1280--light.png | 02 correctness | **Unstyled** (built by the lead's first `web.sh`, which ran Vite outside `apps/web`, so Tailwind emitted a 9 KB stylesheet; text content is valid evidence, the layout is not). Alice's home: L1 "Last result · Gameweek 1 … 4-fold · 54.91" for a round with two void legs (CORR-21) | web_check.mjs, prod bundle on 4320 vs API 8120, scratch data after lifecycle.py |
| results--void-leg-price-unstyled--1280--light.png | 02 correctness | **Unstyled**, as above. L1 Results list: Gameweek 1 at 54.91, void legs multiplied (CORR-21) | same run |
| coupon--settled-void-legs-unstyled--1280--light.png | 02 correctness | **Unstyled**, as above. The same round's settled coupon: 7.44, "2 legs voided — not in the combined price", header "4 of 3" after a leave and an erasure (CORR-21, CORR-26) | same run, reached by tapping the Results row |
| settings--your-data-unstyled--1280--light.png | 05 features | Settings scrolled to "Your data" (Bob): Download my data + Delete my account (FEAT-B07). **Unstyled** — the stylesheet did not apply under the route-fulfilment harness; functional evidence only, not for the design corpus | notes/05-features/browser.mjs PHASES=bob, prod bundle fulfilled on the API origin 8150 |
| settings--delete-confirm-unstyled--1280--light.png | 05 features | Delete confirm panel with PIN entered, not submitted (Bob). Unstyled, as above | same, PHASES=bob |
| login--after-account-deleted-unstyled--1280--light.png | 05 features | /login after Carol deleted her own account through Settings; toast "Your account has been deleted." bottom right. Unstyled, as above | browser.mjs PHASES=b07 |
| home--rename-notice-unstyled--1280--light.png | 05 features | In-app rename notice dialog for an untold renamed profile id (FEAT-A11). Unstyled, as above | browser.mjs PHASES=a11 |
| register--signups-closed-before-submit-unstyled--1280--light.png | 05 features | /register with PUBLIC_SIGNUP_ENABLED=false: the full form, no notice (FEAT-A12). Unstyled, as above | browser.mjs PHASES=a12, stack env PUBLIC_SIGNUP_ENABLED=false |
| register--signups-closed-after-submit-unstyled--1280--light.png | 05 features | The same form after filling name + PIN twice: only now "Sign-ups are closed right now. Ask a league admin for an invite." Unstyled, as above | same |

<!-- lens-03 begin -->
## Lens 03 — UX / accessibility corpus

Production bundle built with `notes/03-ux/build_web.py` (cwd=apps/web, CSS 45.8 KB — the harness
`web.sh` build was unstyled) against the seeded scratch API on :8130 (`ODDS_PROVIDER=fake`,
scheduler off, `notes/03-ux/seed_states.py`). Playwright 1.60 Chromium, deviceScaleFactor 1,
`reducedMotion: reduce`, service workers blocked, theme and session put in localStorage before
first paint. 390 captures use a desktop UA at 390×844 (the layout an installed PWA gets; the
install gate is UA-triggered and is captured separately as `install-gate--mobile-browser`).
Personas: Alice = site admin + league admin of the-coupon; Bob = member; Dave = no league.
Last column: axe-core 4.10.2 violations at capture (`rule:nodes`), `—` = not run.
Duplicate hashes: 8 groups (see `notes/03-ux/duplicates.txt`).

| file | url at capture | state | width | theme | sha256 | state confirmed by | axe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `admin-results--pending-settlement--1280--dark.png` | `/admin/results` | pending-settlement | 1280 | dark | `c1e1b5682515` | Alice: h1 “Results” | 0 |
| `admin-results--pending-settlement--1280--light.png` | `/admin/results` | pending-settlement | 1280 | light | `aa1f925dec34` | Alice: h1 “Results” | 0 |
| `admin-results--pending-settlement--390--dark.png` | `/admin/results` | pending-settlement | 390 | dark | `07572dd7cf2b` | Alice: h1 “Results” | 0 |
| `admin-results--pending-settlement--390--light.png` | `/admin/results` | pending-settlement | 390 | light | `c86bcf572cc0` | Alice: h1 “Results” | 0 |
| `current-round--locked-own--1280--dark.png` | `/leagues/the-coupon/predictions` | locked-own | 1280 | dark | `3d5c37ccb2b1` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked-own--1280--dark--full.png` | `/leagues/the-coupon/predictions` | locked-own (full page) | 1280 | dark | `9b2f0eb0382b` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked-own--1280--light.png` | `/leagues/the-coupon/predictions` | locked-own | 1280 | light | `8f7b4cb663cc` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked-own--1280--light--full.png` | `/leagues/the-coupon/predictions` | locked-own (full page) | 1280 | light | `6c2eb7c00aea` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked-own--390--dark.png` | `/leagues/the-coupon/predictions` | locked-own | 390 | dark | `b7f470e332e7` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked-own--390--dark--full.png` | `/leagues/the-coupon/predictions` | locked-own (full page) | 390 | dark | `d04839c46e72` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked-own--390--light.png` | `/leagues/the-coupon/predictions` | locked-own | 390 | light | `69439e3ba07e` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked-own--390--light--full.png` | `/leagues/the-coupon/predictions` | locked-own (full page) | 390 | light | `717aefb39d95` | Alice: round status locked (API); 'lock' text present | 0 |
| `home--locked--1280--dark.png` | `/` | locked | 1280 | dark | `a65cd186c846` | Alice: round status locked (API); 'lock' text present | 0 |
| `home--locked--1280--light.png` | `/` | locked | 1280 | light | `32457444b87c` | Alice: round status locked (API); 'lock' text present | 0 |
| `home--locked--390--dark.png` | `/` | locked | 390 | dark | `f9ed25f21698` | Alice: round status locked (API); 'lock' text present | 0 |
| `home--locked--390--light.png` | `/` | locked | 390 | light | `6dc078818511` | Alice: round status locked (API); 'lock' text present | 0 |
| `about--happy--1280--dark.png` | `/about` | happy | 1280 | dark | `b82d0aa7ff79` | Alice: h1 “About & scoring rules” | 0 |
| `about--happy--1280--dark--full.png` | `/about` | happy (full page) | 1280 | dark | `3329c3d6dd93` | Alice: h1 “About & scoring rules” | 0 |
| `about--happy--1280--light.png` | `/about` | happy | 1280 | light | `4a250cb590bc` | Alice: h1 “About & scoring rules” | 0 |
| `about--happy--1280--light--full.png` | `/about` | happy (full page) | 1280 | light | `27ba6633c9b3` | Alice: h1 “About & scoring rules” | 0 |
| `about--happy--390--dark.png` | `/about` | happy | 390 | dark | `4729c8fca187` | Alice: h1 “About & scoring rules” | 0 |
| `about--happy--390--dark--full.png` | `/about` | happy (full page) | 390 | dark | `eb38f8a37502` | Alice: h1 “About & scoring rules” | 0 |
| `about--happy--390--light.png` | `/about` | happy | 390 | light | `0e36ea1594f1` | Alice: h1 “About & scoring rules” | 0 |
| `about--happy--390--light--full.png` | `/about` | happy (full page) | 390 | light | `393efdac022c` | Alice: h1 “About & scoring rules” | 0 |
| `admin-calendar--happy--1280--dark.png` | `/admin/calendar` | happy | 1280 | dark | `877c2d9bd5d8` | Alice: h1 “Calendar” | 0 |
| `admin-calendar--happy--1280--light.png` | `/admin/calendar` | happy | 1280 | light | `6d100c807641` | Alice: h1 “Calendar” | 0 |
| `admin-calendar--happy--390--dark.png` | `/admin/calendar` | happy | 390 | dark | `8db2870922dd` | Alice: h1 “Calendar” | 0 |
| `admin-calendar--happy--390--light.png` | `/admin/calendar` | happy | 390 | light | `c4e15cf51004` | Alice: h1 “Calendar” | 0 |
| `admin-dashboard--error--1280--dark.png` | `/admin/dashboard` | error | 1280 | dark | `23081ed140ea` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `admin-dashboard--error--1280--light.png` | `/admin/dashboard` | error | 1280 | light | `e2c032169382` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `admin-dashboard--error--390--dark.png` | `/admin/dashboard` | error | 390 | dark | `35c3a3a1f9f7` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `admin-dashboard--error--390--light.png` | `/admin/dashboard` | error | 390 | light | `2fc3d6e42a85` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `admin-dashboard--happy--1280--dark.png` | `/admin/dashboard` | happy | 1280 | dark | `d4e6cb6527af` | Alice: h1 “Dashboard” | 0 |
| `admin-dashboard--happy--1280--light.png` | `/admin/dashboard` | happy | 1280 | light | `c5574ef3932a` | Alice: h1 “Dashboard” | 0 |
| `admin-dashboard--happy--390--dark.png` | `/admin/dashboard` | happy | 390 | dark | `aeddf565af72` | Alice: h1 “Dashboard” | 0 |
| `admin-dashboard--happy--390--light.png` | `/admin/dashboard` | happy | 390 | light | `b93ed56e1a5b` | Alice: h1 “Dashboard” | 0 |
| `admin-dashboard--loading--1280--dark.png` | `/admin/dashboard` | loading | 1280 | dark | `23081ed140ea` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `admin-dashboard--loading--1280--light.png` | `/admin/dashboard` | loading | 1280 | light | `e2c032169382` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `admin-dashboard--loading--390--dark.png` | `/admin/dashboard` | loading | 390 | dark | `35c3a3a1f9f7` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `admin-dashboard--loading--390--light.png` | `/admin/dashboard` | loading | 390 | light | `2fc3d6e42a85` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `admin-dashboard--not-site-admin--1280--dark.png` | `/` | not-site-admin | 1280 | dark | `94877c9aeae4` | Bob: h1 “Hi Bob” | 0 |
| `admin-dashboard--not-site-admin--1280--light.png` | `/` | not-site-admin | 1280 | light | `f8cccabfbdea` | Bob: h1 “Hi Bob” | 0 |
| `admin-dashboard--not-site-admin--390--dark.png` | `/` | not-site-admin | 390 | dark | `f1061792a985` | Bob: h1 “Hi Bob” | 0 |
| `admin-dashboard--not-site-admin--390--light.png` | `/` | not-site-admin | 390 | light | `2f3c1b73d4b0` | Bob: h1 “Hi Bob” | 0 |
| `admin-invites--happy--1280--dark.png` | `/admin/invites` | happy | 1280 | dark | `f0d5db7c5911` | Alice: h1 “Invites” | 0 |
| `admin-invites--happy--1280--light.png` | `/admin/invites` | happy | 1280 | light | `3c4e9dce025f` | Alice: h1 “Invites” | 0 |
| `admin-invites--happy--390--dark.png` | `/admin/invites` | happy | 390 | dark | `15970d24b8c8` | Alice: h1 “Invites” | 0 |
| `admin-invites--happy--390--light.png` | `/admin/invites` | happy | 390 | light | `731e500bee90` | Alice: h1 “Invites” | 0 |
| `admin-leagues--happy--1280--dark.png` | `/admin/leagues` | happy | 1280 | dark | `efa108303541` | Alice: h1 “All leagues” | 0 |
| `admin-leagues--happy--1280--light.png` | `/admin/leagues` | happy | 1280 | light | `d0a05a46c696` | Alice: h1 “All leagues” | 0 |
| `admin-leagues--happy--390--dark.png` | `/admin/leagues` | happy | 390 | dark | `1e23ec01581b` | Alice: h1 “All leagues” | 0 |
| `admin-leagues--happy--390--light.png` | `/admin/leagues` | happy | 390 | light | `37b08a45a80d` | Alice: h1 “All leagues” | 0 |
| `admin-players--error--1280--dark.png` | `/admin/players` | error | 1280 | dark | `f17dbf0106c5` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `admin-players--error--1280--light.png` | `/admin/players` | error | 1280 | light | `8b5706ae2a45` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `admin-players--error--390--dark.png` | `/admin/players` | error | 390 | dark | `de0434ad261a` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `admin-players--error--390--light.png` | `/admin/players` | error | 390 | light | `9884483b0122` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `admin-players--happy--1280--dark.png` | `/admin/players` | happy | 1280 | dark | `c6bd3985730c` | Alice: h1 “Players” | 0 |
| `admin-players--happy--1280--light.png` | `/admin/players` | happy | 1280 | light | `ac2c95ab9a05` | Alice: h1 “Players” | 0 |
| `admin-players--happy--390--dark.png` | `/admin/players` | happy | 390 | dark | `dc39084f5dad` | Alice: h1 “Players” | 0 |
| `admin-players--happy--390--light.png` | `/admin/players` | happy | 390 | light | `b718abf9f94f` | Alice: h1 “Players” | 0 |
| `admin-players--loading--1280--dark.png` | `/admin/players` | loading | 1280 | dark | `13865a8de08f` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `admin-players--loading--1280--light.png` | `/admin/players` | loading | 1280 | light | `5d29acd32ef9` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `admin-players--loading--390--dark.png` | `/admin/players` | loading | 390 | dark | `7b70b73fcee5` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `admin-players--loading--390--light.png` | `/admin/players` | loading | 390 | light | `3ccdbb5de2c3` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `admin-results--happy--1280--dark.png` | `/admin/results` | happy | 1280 | dark | `665ee7f902eb` | Alice: h1 “Results” | 0 |
| `admin-results--happy--1280--light.png` | `/admin/results` | happy | 1280 | light | `1b8084882a93` | Alice: h1 “Results” | 0 |
| `admin-results--happy--390--dark.png` | `/admin/results` | happy | 390 | dark | `359ed914b333` | Alice: h1 “Results” | 0 |
| `admin-results--happy--390--light.png` | `/admin/results` | happy | 390 | light | `e0bedfccdf80` | Alice: h1 “Results” | 0 |
| `admin-sync--happy--1280--dark.png` | `/admin/sync` | happy | 1280 | dark | `c1e6cd8d10cb` | Alice: h1 “Sync” | 0 |
| `admin-sync--happy--1280--light.png` | `/admin/sync` | happy | 1280 | light | `63bb5560b10f` | Alice: h1 “Sync” | 0 |
| `admin-sync--happy--390--dark.png` | `/admin/sync` | happy | 390 | dark | `aa601f11be69` | Alice: h1 “Sync” | 0 |
| `admin-sync--happy--390--light.png` | `/admin/sync` | happy | 390 | light | `902d0d56db37` | Alice: h1 “Sync” | 0 |
| `career-profile--happy--1280--dark.png` | `/profile` | happy | 1280 | dark | `258118c717be` | Alice: h1 “Alice” | 0 |
| `career-profile--happy--1280--light.png` | `/profile` | happy | 1280 | light | `22d3747fd51b` | Alice: h1 “Alice” | 0 |
| `career-profile--happy--390--dark.png` | `/profile` | happy | 390 | dark | `7b9954db78fa` | Alice: h1 “Alice” | 0 |
| `career-profile--happy--390--light.png` | `/profile` | happy | 390 | light | `8e589cb937f2` | Alice: h1 “Alice” | 0 |
| `coupon--open--1280--dark.png` | `/leagues/the-coupon/predictions` | open | 1280 | dark | `d2bf82fbc847` | Alice: h1 “This week's coupon” | 0 |
| `coupon--open--1280--light.png` | `/leagues/the-coupon/predictions` | open | 1280 | light | `b70650ef2ac1` | Alice: h1 “This week's coupon” | 0 |
| `coupon--open--390--dark.png` | `/leagues/the-coupon/predictions` | open | 390 | dark | `820b8d2c5c16` | Alice: h1 “This week's coupon” | 0 |
| `coupon--open--390--light.png` | `/leagues/the-coupon/predictions` | open | 390 | light | `34c8f711dc0f` | Alice: h1 “This week's coupon” | 0 |
| `create-league--happy--1280--dark.png` | `/leagues/new` | happy | 1280 | dark | `2b4b812039ea` | Alice: h1 “Create a League” | 0 |
| `create-league--happy--1280--light.png` | `/leagues/new` | happy | 1280 | light | `015f4bb19bd5` | Alice: h1 “Create a League” | 0 |
| `create-league--happy--390--dark.png` | `/leagues/new` | happy | 390 | dark | `db91c122f423` | Alice: h1 “Create a League” | 0 |
| `create-league--happy--390--light.png` | `/leagues/new` | happy | 390 | light | `99c3f912b97d` | Alice: h1 “Create a League” | 0 |
| `current-round--error--1280--dark.png` | `/leagues/the-coupon/predictions` | error | 1280 | dark | `137a4d22925a` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `current-round--error--1280--light.png` | `/leagues/the-coupon/predictions` | error | 1280 | light | `b5976533f921` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `current-round--error--390--dark.png` | `/leagues/the-coupon/predictions` | error | 390 | dark | `ee37ad97260b` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `current-round--error--390--light.png` | `/leagues/the-coupon/predictions` | error | 390 | light | `3535e02b7456` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `current-round--loading--1280--dark.png` | `/leagues/the-coupon/predictions` | loading | 1280 | dark | `d983376537d6` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `current-round--loading--1280--light.png` | `/leagues/the-coupon/predictions` | loading | 1280 | light | `64ec95f82a97` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `current-round--loading--390--dark.png` | `/leagues/the-coupon/predictions` | loading | 390 | dark | `dac03983b5bf` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `current-round--loading--390--light.png` | `/leagues/the-coupon/predictions` | loading | 390 | light | `de4b88318489` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `current-round--locked--1280--dark.png` | `/leagues/sunday-club/predictions` | locked | 1280 | dark | `ccbed51790c3` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked--1280--dark--full.png` | `/leagues/sunday-club/predictions` | locked (full page) | 1280 | dark | `65525284118b` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked--1280--light.png` | `/leagues/sunday-club/predictions` | locked | 1280 | light | `66fa217d3152` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked--1280--light--full.png` | `/leagues/sunday-club/predictions` | locked (full page) | 1280 | light | `42d71ca01316` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked--390--dark.png` | `/leagues/sunday-club/predictions` | locked | 390 | dark | `9c096065dc9b` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked--390--dark--full.png` | `/leagues/sunday-club/predictions` | locked (full page) | 390 | dark | `2e840fb4d503` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked--390--light.png` | `/leagues/sunday-club/predictions` | locked | 390 | light | `30a7452490d1` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--locked--390--light--full.png` | `/leagues/sunday-club/predictions` | locked (full page) | 390 | light | `42e1f1a978da` | Alice: round status locked (API); 'lock' text present | 0 |
| `current-round--offline--1280--dark.png` | `/leagues/the-coupon/predictions` | offline | 1280 | dark | `87e7f469569e` | Alice: network dropped after load; 'offline' text present | 0 |
| `current-round--offline--1280--light.png` | `/leagues/the-coupon/predictions` | offline | 1280 | light | `cc937fa1aa3c` | Alice: network dropped after load; 'offline' text present | 0 |
| `current-round--offline--390--dark.png` | `/leagues/the-coupon/predictions` | offline | 390 | dark | `9e534359bc65` | Alice: network dropped after load; 'offline' text present | 0 |
| `current-round--offline--390--light.png` | `/leagues/the-coupon/predictions` | offline | 390 | light | `0a5fce8807f6` | Alice: network dropped after load; 'offline' text present | 0 |
| `current-round--open--1280--dark.png` | `/leagues/the-coupon/predictions` | open | 1280 | dark | `f52fd0f2d9c4` | Alice: h1 “This week's coupon” | 0 |
| `current-round--open--1280--dark--full.png` | `/leagues/the-coupon/predictions` | open (full page) | 1280 | dark | `be49bbd4bcfd` | Alice: h1 “This week's coupon” | 0 |
| `current-round--open--1280--light.png` | `/leagues/the-coupon/predictions` | open | 1280 | light | `ab1a5765848d` | Alice: h1 “This week's coupon” | 0 |
| `current-round--open--1280--light--full.png` | `/leagues/the-coupon/predictions` | open (full page) | 1280 | light | `b21afaa3c7fd` | Alice: h1 “This week's coupon” | 0 |
| `current-round--open--390--dark.png` | `/leagues/the-coupon/predictions` | open | 390 | dark | `2961c070f157` | Alice: h1 “This week's coupon” | 0 |
| `current-round--open--390--dark--full.png` | `/leagues/the-coupon/predictions` | open (full page) | 390 | dark | `f62fc17fd122` | Alice: h1 “This week's coupon” | 0 |
| `current-round--open--390--light.png` | `/leagues/the-coupon/predictions` | open | 390 | light | `3d70532addf9` | Alice: h1 “This week's coupon” | 0 |
| `current-round--open--390--light--full.png` | `/leagues/the-coupon/predictions` | open (full page) | 390 | light | `0f5deaa21a4f` | Alice: h1 “This week's coupon” | 0 |
| `current-round--open-picked--1280--dark.png` | `/leagues/the-coupon/predictions` | open-picked | 1280 | dark | `9191da3da3e8` | Bob: h1 “This week's coupon” | 0 |
| `current-round--open-picked--1280--dark--full.png` | `/leagues/the-coupon/predictions` | open-picked (full page) | 1280 | dark | `eee63fc7a391` | Bob: h1 “This week's coupon” | 0 |
| `current-round--open-picked--1280--light.png` | `/leagues/the-coupon/predictions` | open-picked | 1280 | light | `0ea0290fe0f2` | Bob: h1 “This week's coupon” | 0 |
| `current-round--open-picked--1280--light--full.png` | `/leagues/the-coupon/predictions` | open-picked (full page) | 1280 | light | `9c8d142d32cd` | Bob: h1 “This week's coupon” | 0 |
| `current-round--open-picked--390--dark.png` | `/leagues/the-coupon/predictions` | open-picked | 390 | dark | `dfb2485e94c8` | Bob: h1 “This week's coupon” | 0 |
| `current-round--open-picked--390--dark--full.png` | `/leagues/the-coupon/predictions` | open-picked (full page) | 390 | dark | `e77edc428781` | Bob: h1 “This week's coupon” | 0 |
| `current-round--open-picked--390--light.png` | `/leagues/the-coupon/predictions` | open-picked | 390 | light | `4e39c90ae55f` | Bob: h1 “This week's coupon” | 0 |
| `current-round--open-picked--390--light--full.png` | `/leagues/the-coupon/predictions` | open-picked (full page) | 390 | light | `7dd8a2bfb598` | Bob: h1 “This week's coupon” | 0 |
| `discover-leagues--happy--1280--dark.png` | `/leagues/discover` | happy | 1280 | dark | `0e8672d1a670` | Dave: h1 “Discover Leagues” | 0 |
| `discover-leagues--happy--1280--light.png` | `/leagues/discover` | happy | 1280 | light | `ae8c8949b0da` | Dave: h1 “Discover Leagues” | 0 |
| `discover-leagues--happy--390--dark.png` | `/leagues/discover` | happy | 390 | dark | `8e4f70f30c72` | Dave: h1 “Discover Leagues” | 0 |
| `discover-leagues--happy--390--light.png` | `/leagues/discover` | happy | 390 | light | `1f2c3a3f28cf` | Dave: h1 “Discover Leagues” | 0 |
| `football--error--1280--dark.png` | `/football` | error | 1280 | dark | `352e931697ed` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `football--error--1280--light.png` | `/football` | error | 1280 | light | `27480a453d24` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `football--error--390--dark.png` | `/football` | error | 390 | dark | `ef9ba8e6b79c` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `football--error--390--light.png` | `/football` | error | 390 | light | `d2c58f13366e` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `football--forced-empty--1280--dark.png` | `/football` | forced-empty | 1280 | dark | `2ad5395f5fd5` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL TABLES…” | 0 |
| `football--forced-empty--1280--light.png` | `/football` | forced-empty | 1280 | light | `49ac0f1d4844` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL TABLES…” | 0 |
| `football--forced-empty--390--dark.png` | `/football` | forced-empty | 390 | dark | `8ea780d5339c` | Alice: empty copy present: “THE COUPON AL TABLES & RESULTS Football Stats Tables Results No tables…” | 0 |
| `football--forced-empty--390--light.png` | `/football` | forced-empty | 390 | light | `1d05e949a17a` | Alice: empty copy present: “THE COUPON AL TABLES & RESULTS Football Stats Tables Results No tables…” | 0 |
| `football--happy--1280--dark.png` | `/football` | happy | 1280 | dark | `1ac4ace1a844` | Alice: h1 “Football Stats” | 0 |
| `football--happy--1280--light.png` | `/football` | happy | 1280 | light | `cbc4d4ce9034` | Alice: h1 “Football Stats” | 0 |
| `football--happy--390--dark.png` | `/football` | happy | 390 | dark | `3989a24a3462` | Alice: h1 “Football Stats” | 0 |
| `football--happy--390--light.png` | `/football` | happy | 390 | light | `e9bdbf7afef0` | Alice: h1 “Football Stats” | 0 |
| `football--loading--1280--dark.png` | `/football` | loading | 1280 | dark | `501c3f8d71ba` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `football--loading--1280--light.png` | `/football` | loading | 1280 | light | `5eaf097237ef` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `football--loading--390--dark.png` | `/football` | loading | 390 | dark | `73dc5a17b1fc` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `football--loading--390--light.png` | `/football` | loading | 390 | light | `4500513f3657` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `forgot-pin--happy--1280--dark.png` | `/forgot-pin` | happy | 1280 | dark | `3170bd9ca9f1` | signed out: h1 “Reset PIN” | 0 |
| `forgot-pin--happy--1280--light.png` | `/forgot-pin` | happy | 1280 | light | `1280f8f684f4` | signed out: h1 “Reset PIN” | 0 |
| `forgot-pin--happy--390--dark.png` | `/forgot-pin` | happy | 390 | dark | `c65711fb2005` | signed out: h1 “Reset PIN” | 0 |
| `forgot-pin--happy--390--light.png` | `/forgot-pin` | happy | 390 | light | `8dc37d6ba996` | signed out: h1 “Reset PIN” | 0 |
| `home--error--1280--dark.png` | `/` | error | 1280 | dark | `1595db11a609` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `home--error--1280--light.png` | `/` | error | 1280 | light | `f709581d0636` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `home--error--390--dark.png` | `/` | error | 390 | dark | `01486dbe48fe` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `home--error--390--light.png` | `/` | error | 390 | light | `52bcc7e0b779` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `home--firstrun--1280--dark.png` | `/` | firstrun | 1280 | dark | `28ed2c320d02` | Dave: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Dave DA THE COU…” | 0 |
| `home--firstrun--1280--dark--full.png` | `/` | firstrun (full page) | 1280 | dark | `d21fd257833c` | Dave: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Dave DA THE COU…” | 0 |
| `home--firstrun--1280--light.png` | `/` | firstrun | 1280 | light | `335656449b41` | Dave: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Dave DA THE COU…” | 0 |
| `home--firstrun--1280--light--full.png` | `/` | firstrun (full page) | 1280 | light | `d19668b4bdaa` | Dave: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Dave DA THE COU…” | 0 |
| `home--firstrun--390--dark.png` | `/` | firstrun | 390 | dark | `a84de570fca2` | Dave: empty copy present: “THE COUPON DA THE COUPON · YOUR SEASON Hi Dave Your picks, deadlines a…” | 0 |
| `home--firstrun--390--dark--full.png` | `/` | firstrun (full page) | 390 | dark | `ca00186e6c35` | Dave: empty copy present: “THE COUPON DA THE COUPON · YOUR SEASON Hi Dave Your picks, deadlines a…” | 0 |
| `home--firstrun--390--light.png` | `/` | firstrun | 390 | light | `ae2b788317ff` | Dave: empty copy present: “THE COUPON DA THE COUPON · YOUR SEASON Hi Dave Your picks, deadlines a…” | 0 |
| `home--firstrun--390--light--full.png` | `/` | firstrun (full page) | 390 | light | `e4e56a73aa52` | Dave: empty copy present: “THE COUPON DA THE COUPON · YOUR SEASON Hi Dave Your picks, deadlines a…” | 0 |
| `home--happy--1280--dark.png` | `/` | happy | 1280 | dark | `e2f84f6159d5` | Alice: h1 “Hi Alice” | 0 |
| `home--happy--1280--dark--full.png` | `/` | happy (full page) | 1280 | dark | `6e8de8b6dcde` | Alice: h1 “Hi Alice” | 0 |
| `home--happy--1280--light.png` | `/` | happy | 1280 | light | `c29eacd7a95f` | Alice: h1 “Hi Alice” | 0 |
| `home--happy--1280--light--full.png` | `/` | happy (full page) | 1280 | light | `49245cc83824` | Alice: h1 “Hi Alice” | 0 |
| `home--happy--390--dark.png` | `/` | happy | 390 | dark | `28f2fecf4e94` | Alice: h1 “Hi Alice” | 0 |
| `home--happy--390--dark--full.png` | `/` | happy (full page) | 390 | dark | `8883b8096dc8` | Alice: h1 “Hi Alice” | 0 |
| `home--happy--390--light.png` | `/` | happy | 390 | light | `4bdc1a89d688` | Alice: h1 “Hi Alice” | 0 |
| `home--happy--390--light--full.png` | `/` | happy (full page) | 390 | light | `b1481ba24dc9` | Alice: h1 “Hi Alice” | 0 |
| `home--loading--1280--dark.png` | `/` | loading | 1280 | dark | `cb82e159c437` | Alice: 13 `aria-busy` skeletons in DOM, request held open | 0 |
| `home--loading--1280--light.png` | `/` | loading | 1280 | light | `c7668f353e7f` | Alice: 13 `aria-busy` skeletons in DOM, request held open | 0 |
| `home--loading--390--dark.png` | `/` | loading | 390 | dark | `8c370fa51375` | Alice: 13 `aria-busy` skeletons in DOM, request held open | 0 |
| `home--loading--390--light.png` | `/` | loading | 390 | light | `a917eb7f36c0` | Alice: 13 `aria-busy` skeletons in DOM, request held open | 0 |
| `home--member--1280--dark.png` | `/` | member | 1280 | dark | `24bd240a50e4` | Bob: h1 “Hi Bob” | 0 |
| `home--member--1280--light.png` | `/` | member | 1280 | light | `1787a01704cd` | Bob: h1 “Hi Bob” | 0 |
| `home--member--390--dark.png` | `/` | member | 390 | dark | `062c59c92aa6` | Bob: h1 “Hi Bob” | 0 |
| `home--member--390--light.png` | `/` | member | 390 | light | `9e1050398af2` | Bob: h1 “Hi Bob” | 0 |
| `home--offline--1280--dark.png` | `/` | offline | 1280 | dark | `8a64cdfeffa5` | Alice: network dropped after load; 'offline' text present | 0 |
| `home--offline--1280--light.png` | `/` | offline | 1280 | light | `125de649de1a` | Alice: network dropped after load; 'offline' text present | 0 |
| `home--offline--390--dark.png` | `/` | offline | 390 | dark | `a9f5dcc39892` | Alice: network dropped after load; 'offline' text present | 0 |
| `home--offline--390--light.png` | `/` | offline | 390 | light | `a51264ab6da8` | Alice: network dropped after load; 'offline' text present | 0 |
| `install-gate--mobile-browser--390--dark.png` | `/login` | mobile-browser | 390 | dark | `a4233326411e` | signed out: h1 “One Saturday pick. One shared coupon.” | region:6 |
| `install-gate--mobile-browser--390--light.png` | `/login` | mobile-browser | 390 | light | `6398093c1f2f` | signed out: h1 “One Saturday pick. One shared coupon.” | region:6 |
| `join--happy--1280--dark.png` | `/join/REVIEWINVITE1` | happy | 1280 | dark | `a940471e82ef` | signed out: h1 “Join the league” | 0 |
| `join--happy--1280--light.png` | `/join/REVIEWINVITE1` | happy | 1280 | light | `10d621354fe6` | signed out: h1 “Join the league” | 0 |
| `join--happy--390--dark.png` | `/join/REVIEWINVITE1` | happy | 390 | dark | `898fc6ab9631` | signed out: h1 “Join the league” | 0 |
| `join--happy--390--light.png` | `/join/REVIEWINVITE1` | happy | 390 | light | `ff8c3ab9a56c` | signed out: h1 “Join the league” | 0 |
| `join-by-code--happy--1280--dark.png` | `/leagues/join` | happy | 1280 | dark | `1febf9357405` | Dave: h1 “Join a league” | 0 |
| `join-by-code--happy--1280--light.png` | `/leagues/join` | happy | 1280 | light | `732157d60adf` | Dave: h1 “Join a league” | 0 |
| `join-by-code--happy--390--dark.png` | `/leagues/join` | happy | 390 | dark | `2ab7d3335e7f` | Dave: h1 “Join a league” | 0 |
| `join-by-code--happy--390--light.png` | `/leagues/join` | happy | 390 | light | `da6cb9aedc7e` | Dave: h1 “Join a league” | 0 |
| `league-audit-log--error--1280--dark.png` | `/leagues/the-coupon/admin/audit-log` | error | 1280 | dark | `c7e90d1e334f` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `league-audit-log--error--1280--light.png` | `/leagues/the-coupon/admin/audit-log` | error | 1280 | light | `8e1df9496bb2` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `league-audit-log--error--390--dark.png` | `/leagues/the-coupon/admin/audit-log` | error | 390 | dark | `fe5d9c6d2cdf` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `league-audit-log--error--390--light.png` | `/leagues/the-coupon/admin/audit-log` | error | 390 | light | `43684605b0f3` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `league-audit-log--happy--1280--dark.png` | `/leagues/the-coupon/admin/audit-log` | happy | 1280 | dark | `c7e90d1e334f` | Alice: h1 “Activity” | 0 |
| `league-audit-log--happy--1280--light.png` | `/leagues/the-coupon/admin/audit-log` | happy | 1280 | light | `8e1df9496bb2` | Alice: h1 “Activity” | 0 |
| `league-audit-log--happy--390--dark.png` | `/leagues/the-coupon/admin/audit-log` | happy | 390 | dark | `fe5d9c6d2cdf` | Alice: h1 “Activity” | 0 |
| `league-audit-log--happy--390--light.png` | `/leagues/the-coupon/admin/audit-log` | happy | 390 | light | `43684605b0f3` | Alice: h1 “Activity” | 0 |
| `league-audit-log--loading--1280--dark.png` | `/leagues/the-coupon/admin/audit-log` | loading | 1280 | dark | `35485dd1d2dc` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `league-audit-log--loading--1280--light.png` | `/leagues/the-coupon/admin/audit-log` | loading | 1280 | light | `5add5cdf8922` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `league-audit-log--loading--390--dark.png` | `/leagues/the-coupon/admin/audit-log` | loading | 390 | dark | `f561db802536` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `league-audit-log--loading--390--light.png` | `/leagues/the-coupon/admin/audit-log` | loading | 390 | light | `0bf800d47da1` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `league-invites--happy--1280--dark.png` | `/leagues/the-coupon/admin/invites` | happy | 1280 | dark | `6be45b773ed7` | Alice: h1 “Invites” | 0 |
| `league-invites--happy--1280--light.png` | `/leagues/the-coupon/admin/invites` | happy | 1280 | light | `25d713bc2fa0` | Alice: h1 “Invites” | 0 |
| `league-invites--happy--390--dark.png` | `/leagues/the-coupon/admin/invites` | happy | 390 | dark | `33b7427e667b` | Alice: h1 “Invites” | 0 |
| `league-invites--happy--390--light.png` | `/leagues/the-coupon/admin/invites` | happy | 390 | light | `2a3c14368699` | Alice: h1 “Invites” | 0 |
| `league-members--error--1280--dark.png` | `/leagues/the-coupon/admin/members` | error | 1280 | dark | `c916718d1b69` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `league-members--error--1280--light.png` | `/leagues/the-coupon/admin/members` | error | 1280 | light | `39995fac8e71` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `league-members--error--390--dark.png` | `/leagues/the-coupon/admin/members` | error | 390 | dark | `8038861371e5` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `league-members--error--390--light.png` | `/leagues/the-coupon/admin/members` | error | 390 | light | `9498218c44af` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `league-members--happy--1280--dark.png` | `/leagues/the-coupon/admin/members` | happy | 1280 | dark | `c453243b0f1e` | Alice: h1 “Members” | 0 |
| `league-members--happy--1280--light.png` | `/leagues/the-coupon/admin/members` | happy | 1280 | light | `4ec839a0ce6e` | Alice: h1 “Members” | 0 |
| `league-members--happy--390--dark.png` | `/leagues/the-coupon/admin/members` | happy | 390 | dark | `3f4d50965575` | Alice: h1 “Members” | 0 |
| `league-members--happy--390--light.png` | `/leagues/the-coupon/admin/members` | happy | 390 | light | `22dc2678ce62` | Alice: h1 “Members” | 0 |
| `league-members--loading--1280--dark.png` | `/leagues/the-coupon/admin/members` | loading | 1280 | dark | `de7a0699ec68` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `league-members--loading--1280--light.png` | `/leagues/the-coupon/admin/members` | loading | 1280 | light | `d515c06ac491` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `league-members--loading--390--dark.png` | `/leagues/the-coupon/admin/members` | loading | 390 | dark | `3ef52da11ed5` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `league-members--loading--390--light.png` | `/leagues/the-coupon/admin/members` | loading | 390 | light | `562d4febdc03` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `league-members--not-admin--1280--dark.png` | `/leagues/sunday-club/admin/members` | not-admin | 1280 | dark | `122d64e20008` | Alice: h1 “Members” | 0 |
| `league-members--not-admin--1280--light.png` | `/leagues/sunday-club/admin/members` | not-admin | 1280 | light | `a3043fc29b58` | Alice: h1 “Members” | 0 |
| `league-members--not-admin--390--dark.png` | `/leagues/sunday-club/admin/members` | not-admin | 390 | dark | `64c6fd82ca14` | Alice: h1 “Members” | 0 |
| `league-members--not-admin--390--light.png` | `/leagues/sunday-club/admin/members` | not-admin | 390 | light | `e8a79afa0f35` | Alice: h1 “Members” | 0 |
| `league-requests--happy--1280--dark.png` | `/leagues/the-coupon/admin/requests` | happy | 1280 | dark | `b26f83547da7` | Alice: h1 “Join Requests” | 0 |
| `league-requests--happy--1280--light.png` | `/leagues/the-coupon/admin/requests` | happy | 1280 | light | `0ed9f8fa736b` | Alice: h1 “Join Requests” | 0 |
| `league-requests--happy--390--dark.png` | `/leagues/the-coupon/admin/requests` | happy | 390 | dark | `5e8ca6299926` | Alice: h1 “Join Requests” | 0 |
| `league-requests--happy--390--light.png` | `/leagues/the-coupon/admin/requests` | happy | 390 | light | `e321a30794c1` | Alice: h1 “Join Requests” | 0 |
| `league-settings--happy--1280--dark.png` | `/leagues/the-coupon/admin/settings` | happy | 1280 | dark | `33173c47eaa6` | Alice: h1 “League Settings” | 0 |
| `league-settings--happy--1280--dark--full.png` | `/leagues/the-coupon/admin/settings` | happy (full page) | 1280 | dark | `3d928900970e` | Alice: h1 “League Settings” | 0 |
| `league-settings--happy--1280--light.png` | `/leagues/the-coupon/admin/settings` | happy | 1280 | light | `c93ba1887992` | Alice: h1 “League Settings” | 0 |
| `league-settings--happy--390--dark.png` | `/leagues/the-coupon/admin/settings` | happy | 390 | dark | `93f0ed43c936` | Alice: h1 “League Settings” | 0 |
| `league-settings--happy--390--light.png` | `/leagues/the-coupon/admin/settings` | happy | 390 | light | `c2151db6ec75` | Alice: h1 “League Settings” | 0 |
| `login--happy--1280--dark.png` | `/login` | happy | 1280 | dark | `42dcae5ad14f` | signed out: h1 “Sign in” | 0 |
| `login--happy--1280--light.png` | `/login` | happy | 1280 | light | `4a8f39e2360f` | signed out: h1 “Sign in” | 0 |
| `login--happy--390--dark.png` | `/login` | happy | 390 | dark | `5ba906ca522f` | signed out: h1 “Sign in” | 0 |
| `login--happy--390--light.png` | `/login` | happy | 390 | light | `9f3146e006ff` | signed out: h1 “Sign in” | 0 |
| `my-leagues--error--1280--dark.png` | `/leagues` | error | 1280 | dark | `24f8896b92c3` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `my-leagues--error--1280--light.png` | `/leagues` | error | 1280 | light | `a0d2a21caad3` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `my-leagues--error--390--dark.png` | `/leagues` | error | 390 | dark | `afb9e0381d15` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `my-leagues--error--390--light.png` | `/leagues` | error | 390 | light | `269859118181` | Alice: **no error state rendered** (500 fulfilled) | 0 |
| `my-leagues--firstrun--1280--dark.png` | `/leagues` | firstrun | 1280 | dark | `73e947e4953a` | Dave: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Dave DA You're …” | 0 |
| `my-leagues--firstrun--1280--light.png` | `/leagues` | firstrun | 1280 | light | `055202f673be` | Dave: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Dave DA You're …” | 0 |
| `my-leagues--firstrun--390--dark.png` | `/leagues` | firstrun | 390 | dark | `8ba627ebfe2c` | Dave: empty copy present: “THE COUPON DA You're offline — some content may be outdated My Leagues…” | 0 |
| `my-leagues--firstrun--390--light.png` | `/leagues` | firstrun | 390 | light | `6901290d8224` | Dave: empty copy present: “THE COUPON DA You're offline — some content may be outdated My Leagues…” | 0 |
| `my-leagues--forced-empty--1280--dark.png` | `/leagues` | forced-empty | 1280 | dark | `402583d6324b` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL My Lea…” | 0 |
| `my-leagues--forced-empty--1280--light.png` | `/leagues` | forced-empty | 1280 | light | `64c4423cbd0d` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL My Lea…” | 0 |
| `my-leagues--forced-empty--390--dark.png` | `/leagues` | forced-empty | 390 | dark | `3232be2b2b9c` | Alice: empty copy present: “THE COUPON AL My Leagues Your league hubs, shortcuts, and current stan…” | 0 |
| `my-leagues--forced-empty--390--light.png` | `/leagues` | forced-empty | 390 | light | `b059afc6044e` | Alice: empty copy present: “THE COUPON AL My Leagues Your league hubs, shortcuts, and current stan…” | 0 |
| `my-leagues--happy--1280--dark.png` | `/leagues` | happy | 1280 | dark | `87820a2fc7df` | Alice: h1 “My Leagues” | 0 |
| `my-leagues--happy--1280--light.png` | `/leagues` | happy | 1280 | light | `7548da3b4287` | Alice: h1 “My Leagues” | 0 |
| `my-leagues--happy--390--dark.png` | `/leagues` | happy | 390 | dark | `9861ca01e984` | Alice: h1 “My Leagues” | 0 |
| `my-leagues--happy--390--light.png` | `/leagues` | happy | 390 | light | `ecd2755fe377` | Alice: h1 “My Leagues” | 0 |
| `my-leagues--loading--1280--dark.png` | `/leagues` | loading | 1280 | dark | `062274f38908` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `my-leagues--loading--1280--light.png` | `/leagues` | loading | 1280 | light | `a38996a90b78` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `my-leagues--loading--390--dark.png` | `/leagues` | loading | 390 | dark | `8a9df7c550f3` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `my-leagues--loading--390--light.png` | `/leagues` | loading | 390 | light | `cd83e2930eb6` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `offline-route--happy--1280--dark.png` | `/offline` | happy | 1280 | dark | `fdd3b86059db` | Alice: h1 “You're offline” | 0 |
| `offline-route--happy--1280--light.png` | `/offline` | happy | 1280 | light | `3aa5e111480c` | Alice: h1 “You're offline” | 0 |
| `offline-route--happy--390--dark.png` | `/offline` | happy | 390 | dark | `2e9ab67f2285` | Alice: h1 “You're offline” | 0 |
| `offline-route--happy--390--light.png` | `/offline` | happy | 390 | light | `c7cab5203c79` | Alice: h1 “You're offline” | 0 |
| `player-profile--error--1280--dark.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | error | 1280 | dark | `cddf22906e85` | Alice: **no error state rendered** (500 fulfilled) | page-has-heading-one:1 |
| `player-profile--error--1280--light.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | error | 1280 | light | `393a42e8c008` | Alice: **no error state rendered** (500 fulfilled) | page-has-heading-one:1 |
| `player-profile--error--390--dark.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | error | 390 | dark | `2420b896bb6d` | Alice: **no error state rendered** (500 fulfilled) | page-has-heading-one:1 |
| `player-profile--error--390--light.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | error | 390 | light | `0c2ab58a1c24` | Alice: **no error state rendered** (500 fulfilled) | page-has-heading-one:1 |
| `player-profile--happy--1280--dark.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | happy | 1280 | dark | `4a56a93b5d40` | Alice: h1 “Bob” | color-contrast:4 |
| `player-profile--happy--1280--light.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | happy | 1280 | light | `b15579996f84` | Alice: h1 “Bob” | color-contrast:4 |
| `player-profile--happy--390--dark.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | happy | 390 | dark | `652db4c9ad80` | Alice: h1 “Bob” | color-contrast:3 |
| `player-profile--happy--390--light.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | happy | 390 | light | `d9abb9539b75` | Alice: h1 “Bob” | color-contrast:3 |
| `player-profile--loading--1280--dark.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | loading | 1280 | dark | `eab7dd1078f8` | Alice: 5 `aria-busy` skeletons in DOM, request held open | page-has-heading-one:1 |
| `player-profile--loading--1280--light.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | loading | 1280 | light | `3473831d33f8` | Alice: 5 `aria-busy` skeletons in DOM, request held open | page-has-heading-one:1 |
| `player-profile--loading--390--dark.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | loading | 390 | dark | `e74b09beeed6` | Alice: 5 `aria-busy` skeletons in DOM, request held open | page-has-heading-one:1 |
| `player-profile--loading--390--light.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | loading | 390 | light | `48fe8dde59f7` | Alice: 5 `aria-busy` skeletons in DOM, request held open | page-has-heading-one:1 |
| `register--happy--1280--dark.png` | `/register` | happy | 1280 | dark | `3dcdbc654364` | signed out: h1 “Create account” | 0 |
| `register--happy--1280--light.png` | `/register` | happy | 1280 | light | `484c65a7741f` | signed out: h1 “Create account” | 0 |
| `register--happy--390--dark.png` | `/register` | happy | 390 | dark | `52c6b270367f` | signed out: h1 “Create account” | 0 |
| `register--happy--390--light.png` | `/register` | happy | 390 | light | `d1f9a0d13a65` | signed out: h1 “Create account” | 0 |
| `results--archive-season--1280--dark.png` | `/leagues/the-coupon/predictions/results` | archive-season | 1280 | dark | `d6abde12d1a3` | Alice: h1 “Season” | 0 |
| `results--archive-season--1280--light.png` | `/leagues/the-coupon/predictions/results` | archive-season | 1280 | light | `413b70dccb3b` | Alice: h1 “Season” | 0 |
| `results--archive-season--390--dark.png` | `/leagues/the-coupon/predictions/results` | archive-season | 390 | dark | `459ea9ac44b4` | Alice: h1 “Season” | 0 |
| `results--archive-season--390--light.png` | `/leagues/the-coupon/predictions/results` | archive-season | 390 | light | `f5ebfed995ab` | Alice: h1 “Season” | 0 |
| `results--empty--1280--dark.png` | `/leagues/sunday-club/predictions/results` | empty | 1280 | dark | `e0fe0d225721` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL SUNDAY…” | 0 |
| `results--empty--1280--light.png` | `/leagues/sunday-club/predictions/results` | empty | 1280 | light | `09c273865bc5` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL SUNDAY…” | 0 |
| `results--empty--390--dark.png` | `/leagues/sunday-club/predictions/results` | empty | 390 | dark | `52d83584c8d1` | Alice: empty copy present: “THE COUPON AL SUNDAY CLUB · EVERY SETTLED GAMEWEEK Season YOUR LEAGUES…” | 0 |
| `results--empty--390--light.png` | `/leagues/sunday-club/predictions/results` | empty | 390 | light | `91dde0615172` | Alice: empty copy present: “THE COUPON AL SUNDAY CLUB · EVERY SETTLED GAMEWEEK Season YOUR LEAGUES…” | 0 |
| `results--error--1280--dark.png` | `/leagues/the-coupon/predictions/results` | error | 1280 | dark | `640a4549c866` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `results--error--1280--light.png` | `/leagues/the-coupon/predictions/results` | error | 1280 | light | `ee13412ab4e5` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `results--error--390--dark.png` | `/leagues/the-coupon/predictions/results` | error | 390 | dark | `18b7ce722761` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `results--error--390--light.png` | `/leagues/the-coupon/predictions/results` | error | 390 | light | `54bd9ec320e7` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `results--forced-empty--1280--dark.png` | `/leagues/the-coupon/predictions/results` | forced-empty | 1280 | dark | `d37b7334f128` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL THE CO…” | 0 |
| `results--forced-empty--1280--light.png` | `/leagues/the-coupon/predictions/results` | forced-empty | 1280 | light | `03909cf6e55a` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL THE CO…” | 0 |
| `results--forced-empty--390--dark.png` | `/leagues/the-coupon/predictions/results` | forced-empty | 390 | dark | `e1040f0e0350` | Alice: empty copy present: “THE COUPON AL THE COUPON TEST LEAGUE · EVERY SETTLED GAMEWEEK Season Y…” | 0 |
| `results--forced-empty--390--light.png` | `/leagues/the-coupon/predictions/results` | forced-empty | 390 | light | `acafcb908112` | Alice: empty copy present: “THE COUPON AL THE COUPON TEST LEAGUE · EVERY SETTLED GAMEWEEK Season Y…” | 0 |
| `results--loading--1280--dark.png` | `/leagues/the-coupon/predictions/results` | loading | 1280 | dark | `f3bb6b356979` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `results--loading--1280--light.png` | `/leagues/the-coupon/predictions/results` | loading | 1280 | light | `a2e7b4476353` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `results--loading--390--dark.png` | `/leagues/the-coupon/predictions/results` | loading | 390 | dark | `cc1d54b19ca9` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `results--loading--390--light.png` | `/leagues/the-coupon/predictions/results` | loading | 390 | light | `bc34735e4958` | Alice: 3 `aria-busy` skeletons in DOM, request held open | 0 |
| `set-pin--happy--1280--dark.png` | `/set-pin?name=Dana` | happy | 1280 | dark | `c87b43ad4661` | signed out: h1 “Choose a new PIN” | 0 |
| `set-pin--happy--1280--light.png` | `/set-pin?name=Dana` | happy | 1280 | light | `9cebf66b0e97` | signed out: h1 “Choose a new PIN” | 0 |
| `set-pin--happy--390--dark.png` | `/set-pin?name=Dana` | happy | 390 | dark | `eaec22508176` | signed out: h1 “Choose a new PIN” | 0 |
| `set-pin--happy--390--light.png` | `/set-pin?name=Dana` | happy | 390 | light | `4e6e0f498891` | signed out: h1 “Choose a new PIN” | 0 |
| `settings--happy--1280--dark.png` | `/settings` | happy | 1280 | dark | `06d98f595c40` | Alice: h1 “Settings” | 0 |
| `settings--happy--1280--dark--full.png` | `/settings` | happy (full page) | 1280 | dark | `bc0126dd93f0` | Alice: h1 “Settings” | 0 |
| `settings--happy--1280--light.png` | `/settings` | happy | 1280 | light | `d32b7325ee9d` | Alice: h1 “Settings” | 0 |
| `settings--happy--1280--light--full.png` | `/settings` | happy (full page) | 1280 | light | `fc15797b7660` | Alice: h1 “Settings” | 0 |
| `settings--happy--390--dark.png` | `/settings` | happy | 390 | dark | `6dc9d23a1e0d` | Alice: h1 “Settings” | 0 |
| `settings--happy--390--dark--full.png` | `/settings` | happy (full page) | 390 | dark | `147963def3ee` | Alice: h1 “Settings” | 0 |
| `settings--happy--390--light.png` | `/settings` | happy | 390 | light | `33b40c2eee85` | Alice: h1 “Settings” | 0 |
| `settings--happy--390--light--full.png` | `/settings` | happy (full page) | 390 | light | `4c960bb24921` | Alice: h1 “Settings” | 0 |
| `standings--archive--1280--dark.png` | `/leagues/the-coupon/leaderboard?season=2025` | archive | 1280 | dark | `38bd8675f684` | Alice: h1 “The Coupon Test League” | 0 |
| `standings--archive--1280--light.png` | `/leagues/the-coupon/leaderboard?season=2025` | archive | 1280 | light | `e46a1cf3ec43` | Alice: h1 “The Coupon Test League” | 0 |
| `standings--archive--390--dark.png` | `/leagues/the-coupon/leaderboard?season=2025` | archive | 390 | dark | `6d8f41c9c5aa` | Alice: h1 “The Coupon Test League” | 0 |
| `standings--archive--390--dark--full.png` | `/leagues/the-coupon/leaderboard?season=2025` | archive (full page) | 390 | dark | `ff2046227dc4` | Alice: h1 “The Coupon Test League” | 0 |
| `standings--archive--390--light.png` | `/leagues/the-coupon/leaderboard?season=2025` | archive | 390 | light | `b29108f200c9` | Alice: h1 “The Coupon Test League” | 0 |
| `standings--archive--390--light--full.png` | `/leagues/the-coupon/leaderboard?season=2025` | archive (full page) | 390 | light | `1b6a751166b6` | Alice: h1 “The Coupon Test League” | 0 |
| `standings--error--1280--dark.png` | `/leagues/the-coupon/leaderboard` | error | 1280 | dark | `e33a6b0af55b` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `standings--error--1280--light.png` | `/leagues/the-coupon/leaderboard` | error | 1280 | light | `5b59e813184c` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `standings--error--390--dark.png` | `/leagues/the-coupon/leaderboard` | error | 390 | dark | `1674e0a1333b` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `standings--error--390--light.png` | `/leagues/the-coupon/leaderboard` | error | 390 | light | `51b5f82ce738` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `standings--forced-empty--1280--dark.png` | `/leagues/the-coupon/leaderboard` | forced-empty | 1280 | dark | `ae0b4a22a58f` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL 2026/2…” | 0 |
| `standings--forced-empty--1280--light.png` | `/leagues/the-coupon/leaderboard` | forced-empty | 1280 | light | `49e71e5b946a` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL 2026/2…” | 0 |
| `standings--forced-empty--390--dark.png` | `/leagues/the-coupon/leaderboard` | forced-empty | 390 | dark | `b402714c5555` | Alice: empty copy present: “THE COUPON AL 2026/27 STANDINGS The Coupon Test League Manage YOUR LEA…” | 0 |
| `standings--forced-empty--390--light.png` | `/leagues/the-coupon/leaderboard` | forced-empty | 390 | light | `9a41490dfa28` | Alice: empty copy present: “THE COUPON AL 2026/27 STANDINGS The Coupon Test League Manage YOUR LEA…” | 0 |
| `standings--happy--1280--dark.png` | `/leagues/the-coupon/leaderboard` | happy | 1280 | dark | `9a8cba22a1c7` | Alice: h1 “The Coupon Test League” | 0 |
| `standings--happy--1280--light.png` | `/leagues/the-coupon/leaderboard` | happy | 1280 | light | `63c37007bd58` | Alice: h1 “The Coupon Test League” | 0 |
| `standings--happy--390--dark.png` | `/leagues/the-coupon/leaderboard` | happy | 390 | dark | `a2b3ece76a59` | Alice: h1 “The Coupon Test League” | 0 |
| `standings--happy--390--light.png` | `/leagues/the-coupon/leaderboard` | happy | 390 | light | `decd7988f25e` | Alice: h1 “The Coupon Test League” | 0 |
| `standings--loading--1280--dark.png` | `/leagues/the-coupon/leaderboard` | loading | 1280 | dark | `d701a4b3ce25` | Alice: 6 `aria-busy` skeletons in DOM, request held open | 0 |
| `standings--loading--1280--light.png` | `/leagues/the-coupon/leaderboard` | loading | 1280 | light | `702223bdb8e6` | Alice: 6 `aria-busy` skeletons in DOM, request held open | 0 |
| `standings--loading--390--dark.png` | `/leagues/the-coupon/leaderboard` | loading | 390 | dark | `5beafdc6a5a0` | Alice: 6 `aria-busy` skeletons in DOM, request held open | 0 |
| `standings--loading--390--light.png` | `/leagues/the-coupon/leaderboard` | loading | 390 | light | `3c8c79b5008a` | Alice: 6 `aria-busy` skeletons in DOM, request held open | 0 |
| `standings--no-settled-rounds--1280--dark.png` | `/leagues/sunday-club/leaderboard` | no-settled-rounds | 1280 | dark | `fc80b66b5ad4` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL 2026/2…” | 0 |
| `standings--no-settled-rounds--1280--light.png` | `/leagues/sunday-club/leaderboard` | no-settled-rounds | 1280 | light | `769ff3785e21` | Alice: empty copy present: “THE COUPON Home Coupon Football Stats Leagues Settings Alice AL 2026/2…” | 0 |
| `standings--no-settled-rounds--390--dark.png` | `/leagues/sunday-club/leaderboard` | no-settled-rounds | 390 | dark | `bb3cee2e55eb` | Alice: empty copy present: “THE COUPON AL 2026/27 STANDINGS Sunday Club Leave YOUR LEAGUES TAP TO …” | 0 |
| `standings--no-settled-rounds--390--light.png` | `/leagues/sunday-club/leaderboard` | no-settled-rounds | 390 | light | `844f918c95ba` | Alice: empty copy present: “THE COUPON AL 2026/27 STANDINGS Sunday Club Leave YOUR LEAGUES TAP TO …” | 0 |
| `standings--offline--1280--dark.png` | `/leagues/the-coupon/leaderboard` | offline | 1280 | dark | `6167eee1aec5` | Alice: network dropped after load; 'offline' text present | 0 |
| `standings--offline--1280--light.png` | `/leagues/the-coupon/leaderboard` | offline | 1280 | light | `b6be6b23af46` | Alice: network dropped after load; 'offline' text present | 0 |
| `standings--offline--390--dark.png` | `/leagues/the-coupon/leaderboard` | offline | 390 | dark | `0b7746998d31` | Alice: network dropped after load; 'offline' text present | 0 |
| `standings--offline--390--light.png` | `/leagues/the-coupon/leaderboard` | offline | 390 | light | `ebc64c806d55` | Alice: network dropped after load; 'offline' text present | 0 |
| `team-season--error--1280--dark.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | error | 1280 | dark | `3b579b679754` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `team-season--error--1280--light.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | error | 1280 | light | `62c2006bda09` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `team-season--error--390--dark.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | error | 390 | dark | `67d14b16049b` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `team-season--error--390--light.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | error | 390 | light | `b90e8580d8a2` | Alice: `query-error-state` present (1), API fulfilled 500 | 0 |
| `team-season--happy--1280--dark.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | happy | 1280 | dark | `fe192b45ef2a` | Alice: h1 “Arsenal FC” | 0 |
| `team-season--happy--1280--light.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | happy | 1280 | light | `549821f34b2c` | Alice: h1 “Arsenal FC” | 0 |
| `team-season--happy--390--dark.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | happy | 390 | dark | `42718f6e4262` | Alice: h1 “Arsenal FC” | 0 |
| `team-season--happy--390--light.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | happy | 390 | light | `fd46e1aabb11` | Alice: h1 “Arsenal FC” | 0 |
| `team-season--loading--1280--dark.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | loading | 1280 | dark | `536820f1eab8` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `team-season--loading--1280--light.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | loading | 1280 | light | `13bf92c75ef8` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `team-season--loading--390--dark.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | loading | 390 | dark | `654dd4640856` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `team-season--loading--390--light.png` | `/football/teams/3426bd61-7ded-4593-81ac-ed5fab0389b7?competition=10932509&season=2025` | loading | 390 | light | `9f5e1115f500` | Alice: 2 `aria-busy` skeletons in DOM, request held open | 0 |
| `welcome--happy--1280--dark.png` | `/welcome` | happy | 1280 | dark | `c64d0fe01888` | signed out: h1 “One Saturday pick. One shared coupon.” | 0 |
| `welcome--happy--1280--light.png` | `/welcome` | happy | 1280 | light | `3a92064e073f` | signed out: h1 “One Saturday pick. One shared coupon.” | 0 |
| `welcome--happy--390--dark.png` | `/welcome` | happy | 390 | dark | `1c9b129f4160` | signed out: h1 “One Saturday pick. One shared coupon.” | 0 |
| `welcome--happy--390--light.png` | `/welcome` | happy | 390 | light | `c6fb65a090ee` | signed out: h1 “One Saturday pick. One shared coupon.” | 0 |
| `career-profile--error--1280--dark.png` | `/profile` | error | 1280 | dark | `e4f33598f3eb` | Alice: `query-error-state` present (1), API fulfilled 500 | page-has-heading-one:1 |
| `career-profile--error--1280--light.png` | `/profile` | error | 1280 | light | `bd54f8993c24` | Alice: `query-error-state` present (1), API fulfilled 500 | page-has-heading-one:1 |
| `career-profile--error--390--dark.png` | `/profile` | error | 390 | dark | `30218c2343fa` | Alice: `query-error-state` present (1), API fulfilled 500 | page-has-heading-one:1 |
| `career-profile--error--390--light.png` | `/profile` | error | 390 | light | `6102fb3f0acc` | Alice: `query-error-state` present (1), API fulfilled 500 | page-has-heading-one:1 |
| `career-profile--loading--1280--dark.png` | `/profile` | loading | 1280 | dark | `a2e21a0fb80e` | Alice: 4 `aria-busy` skeletons in DOM, request held open | page-has-heading-one:1 |
| `career-profile--loading--1280--light.png` | `/profile` | loading | 1280 | light | `c86ed60a0705` | Alice: 4 `aria-busy` skeletons in DOM, request held open | page-has-heading-one:1 |
| `career-profile--loading--390--dark.png` | `/profile` | loading | 390 | dark | `d9742fd99488` | Alice: 4 `aria-busy` skeletons in DOM, request held open | page-has-heading-one:1 |
| `career-profile--loading--390--light.png` | `/profile` | loading | 390 | light | `f63a8e762698` | Alice: 4 `aria-busy` skeletons in DOM, request held open | page-has-heading-one:1 |
| `football--results--1280--dark.png` | `/football?date=2026-05-02` | results | 1280 | dark | `e956a2fce330` | Alice: h1 “Football Stats” | 0 |
| `football--results--1280--light.png` | `/football?date=2026-05-02` | results | 1280 | light | `9689bbc1dab1` | Alice: h1 “Football Stats” | 0 |
| `football--results--390--dark.png` | `/football?date=2026-05-02` | results | 390 | dark | `b48ecd5168c7` | Alice: h1 “Football Stats” | 0 |
| `football--results--390--light.png` | `/football?date=2026-05-02` | results | 390 | light | `4b4cce16d878` | Alice: h1 “Football Stats” | 0 |
| `career-profile--settled--1280--dark.png` | `/profile` | settled | 1280 | dark | `037768d6b7f5` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `career-profile--settled--1280--light.png` | `/profile` | settled | 1280 | light | `6b4b80b70356` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `career-profile--settled--390--dark.png` | `/profile` | settled | 390 | dark | `779760f2db30` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `career-profile--settled--390--light.png` | `/profile` | settled | 390 | light | `5a809e462282` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `coupon--settled--1280--dark.png` | `/leagues/the-coupon/predictions` | settled | 1280 | dark | `3fe07f7b1d26` | Alice: won/lost/settled text present after `/__e2e/settle` | color-contrast:4 |
| `coupon--settled--1280--light.png` | `/leagues/the-coupon/predictions` | settled | 1280 | light | `ec34ad4f24a1` | Alice: won/lost/settled text present after `/__e2e/settle` | color-contrast:4 |
| `coupon--settled--390--dark.png` | `/leagues/the-coupon/predictions` | settled | 390 | dark | `fcb01905e9d9` | Alice: won/lost/settled text present after `/__e2e/settle` | color-contrast:4 |
| `coupon--settled--390--light.png` | `/leagues/the-coupon/predictions` | settled | 390 | light | `2d83acc9e81e` | Alice: won/lost/settled text present after `/__e2e/settle` | color-contrast:4 |
| `current-round--settled--1280--dark.png` | `/leagues/the-coupon/predictions` | settled | 1280 | dark | `e6c9e665e16e` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `current-round--settled--1280--dark--full.png` | `/leagues/the-coupon/predictions` | settled (full page) | 1280 | dark | `2cfbc70976d7` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `current-round--settled--1280--light.png` | `/leagues/the-coupon/predictions` | settled | 1280 | light | `0c636b68f1c2` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `current-round--settled--1280--light--full.png` | `/leagues/the-coupon/predictions` | settled (full page) | 1280 | light | `992b1614ca0e` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `current-round--settled--390--dark.png` | `/leagues/the-coupon/predictions` | settled | 390 | dark | `804a2bac239f` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `current-round--settled--390--dark--full.png` | `/leagues/the-coupon/predictions` | settled (full page) | 390 | dark | `59b358594f09` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `current-round--settled--390--light.png` | `/leagues/the-coupon/predictions` | settled | 390 | light | `f63a20b9ba01` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `current-round--settled--390--light--full.png` | `/leagues/the-coupon/predictions` | settled (full page) | 390 | light | `d8254e83bb27` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `home--settled--1280--dark.png` | `/` | settled | 1280 | dark | `007712d80abd` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `home--settled--1280--dark--full.png` | `/` | settled (full page) | 1280 | dark | `42114b0fbf35` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `home--settled--1280--light.png` | `/` | settled | 1280 | light | `5d592a4a8c3d` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `home--settled--1280--light--full.png` | `/` | settled (full page) | 1280 | light | `e55c9d21e013` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `home--settled--390--dark.png` | `/` | settled | 390 | dark | `b3aee0d4b8b7` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `home--settled--390--dark--full.png` | `/` | settled (full page) | 390 | dark | `d3673f098174` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `home--settled--390--light.png` | `/` | settled | 390 | light | `b07d67766b18` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `home--settled--390--light--full.png` | `/` | settled (full page) | 390 | light | `e0312753efcb` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `player-profile--settled--1280--dark.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | settled | 1280 | dark | `1f3f26145c54` | Alice: won/lost/settled text present after `/__e2e/settle` | color-contrast:8 |
| `player-profile--settled--1280--light.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | settled | 1280 | light | `aff584f8cae4` | Alice: won/lost/settled text present after `/__e2e/settle` | color-contrast:8 |
| `player-profile--settled--390--dark.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | settled | 390 | dark | `21bc70abaa28` | Alice: won/lost/settled text present after `/__e2e/settle` | color-contrast:6 |
| `player-profile--settled--390--light.png` | `/leagues/the-coupon/players/63cb9150-a1cd-455a-898a-d7fb8b1f47f4` | settled | 390 | light | `e7b56c967bf1` | Alice: won/lost/settled text present after `/__e2e/settle` | color-contrast:6 |
| `results--settled--1280--dark.png` | `/leagues/the-coupon/predictions/results` | settled | 1280 | dark | `9f4526a64762` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `results--settled--1280--light.png` | `/leagues/the-coupon/predictions/results` | settled | 1280 | light | `0482ebcc6e03` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `results--settled--390--dark.png` | `/leagues/the-coupon/predictions/results` | settled | 390 | dark | `1b4a15e2349c` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `results--settled--390--light.png` | `/leagues/the-coupon/predictions/results` | settled | 390 | light | `2e9db6ca90c5` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `standings--settled--1280--dark.png` | `/leagues/the-coupon/leaderboard` | settled | 1280 | dark | `fd270c744fd7` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `standings--settled--1280--light.png` | `/leagues/the-coupon/leaderboard` | settled | 1280 | light | `118a9e7d8703` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `standings--settled--390--dark.png` | `/leagues/the-coupon/leaderboard` | settled | 390 | dark | `c6c52921129a` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `standings--settled--390--light.png` | `/leagues/the-coupon/leaderboard` | settled | 390 | light | `756765cb737a` | Alice: won/lost/settled text present after `/__e2e/settle` | 0 |
| `current-round--pick-confirm--390--light.png` | `/leagues/the-coupon/predictions` | pick-confirm | 390 | light | `805cd41470b3` | Carol, real POST by Carol: success toast "Grabbed Arsenal @ 1.90"…; role=status; gap to tab bar 15px, to viewport bottom 76px | — |
| `current-round--pick-conflict--390--light.png` | `/leagues/the-coupon/predictions` | pick-conflict | 390 | light | `521cfddeb758` | Alice, POST fulfilled 409 SELECTION_TAKEN (API shape, mocked; see notes): warning toast "Someone in your league just grabbed that selection — pick a…; role=alert; gap to tab bar 15px, to viewport bottom 76px | — |
| `current-round--pick-pricemoved--390--light.png` | `/leagues/the-coupon/predictions` | pick-pricemoved | 390 | light | `6f50f6edccd3` | Alice, POST fulfilled 409 PRICE_MOVED:9.99 (API shape, mocked): warning toast "That price moved before your pick landed — it’s now 9.99. T…; role=alert; gap to tab bar 15px, to viewport bottom 76px | — |
| `current-round--pick-busy--390--light.png` | `/leagues/the-coupon/predictions` | pick-busy | 390 | light | `a78088a90c07` | Alice, POST fulfilled 429 PICKS_BUSY (mocked): error toast "Too many picks are being made in your league right now — yo…; role=alert; gap to tab bar 15px, to viewport bottom 76px | — |
| `current-round--toast-error--390--light.png` | `/leagues/the-coupon/predictions` | toast-error | 390 | light | `a7c667653bc4` | Alice, POST fulfilled 500 (mocked): error toast "Internal Server Error"…; role=alert; gap to tab bar 15px, to viewport bottom 76px | — |
| `current-round--pick-confirm--390--dark.png` | `/leagues/the-coupon/predictions` | pick-confirm | 390 | dark | `5cb4c2d5d4c8` | Carol, real POST by Carol: success toast "Grabbed The Draw @ 3.75"…; role=status; gap to tab bar 15px, to viewport bottom 76px | — |
| `current-round--pick-pricemoved--390--dark.png` | `/leagues/the-coupon/predictions` | pick-pricemoved | 390 | dark | `07212f165178` | Alice, POST fulfilled 409 PRICE_MOVED:9.99 (API shape, mocked): warning toast "That price moved before your pick landed — it’s now 9.99. T…; role=alert; gap to tab bar 15px, to viewport bottom 76px | — |
| `current-round--pick-busy--390--dark.png` | `/leagues/the-coupon/predictions` | pick-busy | 390 | dark | `0bc13440824a` | Alice, POST fulfilled 429 PICKS_BUSY (mocked): error toast "Too many picks are being made in your league right now — yo…; role=alert; gap to tab bar 15px, to viewport bottom 76px | — |
| `current-round--toast-error--390--dark.png` | `/leagues/the-coupon/predictions` | toast-error | 390 | dark | `1c3bab9a3a58` | Alice, POST fulfilled 500 (mocked): error toast "Internal Server Error"…; role=alert; gap to tab bar 15px, to viewport bottom 76px | — |
| `current-round--pick-confirm--1280--light.png` | `/leagues/the-coupon/predictions` | pick-confirm | 1280 | light | `24297806e474` | Carol, real POST by Carol: success toast "Grabbed Arsenal @ 1.90"…; role=status; gap to tab bar nullpx, to viewport bottom 32px | — |
| `current-round--pick-pricemoved--1280--light.png` | `/leagues/the-coupon/predictions` | pick-pricemoved | 1280 | light | `05f88853ba96` | Alice, POST fulfilled 409 PRICE_MOVED:9.99 (API shape, mocked): warning toast "That price moved before your pick landed — it’s now 9.99. T…; role=alert; gap to tab bar nullpx, to viewport bottom 32px | — |
| `current-round--pick-busy--1280--light.png` | `/leagues/the-coupon/predictions` | pick-busy | 1280 | light | `2f41ff7d8724` | Alice, POST fulfilled 429 PICKS_BUSY (mocked): error toast "Too many picks are being made in your league right now — yo…; role=alert; gap to tab bar nullpx, to viewport bottom 32px | — |
| `current-round--toast-error--1280--light.png` | `/leagues/the-coupon/predictions` | toast-error | 1280 | light | `d121e7119f4c` | Alice, POST fulfilled 500 (mocked): error toast "Internal Server Error"…; role=alert; gap to tab bar nullpx, to viewport bottom 32px | — |
| `current-round--pick-confirm--1280--dark.png` | `/leagues/the-coupon/predictions` | pick-confirm | 1280 | dark | `6c889e78d762` | Carol, real POST by Carol: success toast "Grabbed The Draw @ 3.75"…; role=status; gap to tab bar nullpx, to viewport bottom 32px | — |
| `current-round--pick-pricemoved--1280--dark.png` | `/leagues/the-coupon/predictions` | pick-pricemoved | 1280 | dark | `ea5029318728` | Alice, POST fulfilled 409 PRICE_MOVED:9.99 (API shape, mocked): warning toast "That price moved before your pick landed — it’s now 9.99. T…; role=alert; gap to tab bar nullpx, to viewport bottom 32px | — |
| `current-round--pick-busy--1280--dark.png` | `/leagues/the-coupon/predictions` | pick-busy | 1280 | dark | `02092a6a02c2` | Alice, POST fulfilled 429 PICKS_BUSY (mocked): error toast "Too many picks are being made in your league right now — yo…; role=alert; gap to tab bar nullpx, to viewport bottom 32px | — |
| `current-round--toast-error--1280--dark.png` | `/leagues/the-coupon/predictions` | toast-error | 1280 | dark | `594b178d507c` | Alice, POST fulfilled 500 (mocked): error toast "Internal Server Error"…; role=alert; gap to tab bar nullpx, to viewport bottom 32px | — |
| `current-round--toast-error-safearea34--390--dark.png` | `/leagues/the-coupon/predictions` | toast-error-safearea34 | 390 | dark | `2c4dc7f00b60` | Alice, POST fulfilled 500 (mocked): error toast "Internal Server Error"…; role=alert; gap to tab bar 15px, to viewport bottom 110px | — |
| `current-round--pick-conflict--390--dark.png` | `/leagues/the-coupon/predictions` | pick-conflict | 390 | dark | `e4de16582ea8` | Alice, POST fulfilled 409 SELECTION_TAKEN (API shape, mocked; see notes): warning toast "Someone in your league just grabbed that selection — pick a…; role=alert; gap to tab bar 15px, to viewport bottom 76px | — |
| `current-round--pick-conflict--1280--light.png` | `/leagues/the-coupon/predictions` | pick-conflict | 1280 | light | `2214522c040d` | Alice, POST fulfilled 409 SELECTION_TAKEN (API shape, mocked; see notes): warning toast "Someone in your league just grabbed that selection — pick a…; role=alert; gap to tab bar nullpx, to viewport bottom 32px | — |
| `current-round--pick-conflict--1280--dark.png` | `/leagues/the-coupon/predictions` | pick-conflict | 1280 | dark | `c8ed3ce5c86b` | Alice, POST fulfilled 409 SELECTION_TAKEN (API shape, mocked; see notes): warning toast "Someone in your league just grabbed that selection — pick a…; role=alert; gap to tab bar nullpx, to viewport bottom 32px | — |
| `current-round--offline-queued--1280--dark.png` | `/leagues/sunday-club/predictions` | offline-queued | 1280 | dark | `7aa6ba7bf0ac` | Alice, Chromium offline emulation after load, one selection tapped: spinner on it, every selection disabled, no toast, no 'waiting to send' marker, 0 POSTs (offline-verify.txt); pick landed after reconnect (offline.txt) | — |
| `current-round--offline-queued--1280--light.png` | `/leagues/sunday-club/predictions` | offline-queued | 1280 | light | `cd4773caf80c` | Alice, Chromium offline emulation after load, one selection tapped: spinner on it, every selection disabled, no toast, no 'waiting to send' marker, 0 POSTs (offline-verify.txt); pick landed after reconnect (offline.txt) | — |
| `current-round--offline-queued--390--dark.png` | `/leagues/sunday-club/predictions` | offline-queued | 390 | dark | `c1c97e6ad8ea` | Alice, Chromium offline emulation after load, one selection tapped: spinner on it, every selection disabled, no toast, no 'waiting to send' marker, 0 POSTs (offline-verify.txt); pick landed after reconnect (offline.txt) | — |
| `current-round--offline-queued--390--light.png` | `/leagues/sunday-club/predictions` | offline-queued | 390 | light | `e8edeb34899f` | Alice, Chromium offline emulation after load, one selection tapped: spinner on it, every selection disabled, no toast, no 'waiting to send' marker, 0 POSTs (offline-verify.txt); pick landed after reconnect (offline.txt) | — |
<!-- lens-03 end -->

<!-- lens-06 begin -->
## Lens 06 — premium design corpus additions

Production bundle built by `notes/06-design/build_web.py` (cwd=apps/web, CSS 45,794 B — the same
file name, `index-Br02Ny1y.css`, that production serves) against the lens 06 stack on :8160
(`notes/06-design/stack_design.py`: the e2e server + a test-only `POST /__review/move-price`;
`ODDS_PROVIDER=fake`, scheduler off). Playwright Chromium, deviceScaleFactor 1, reduced motion,
service workers blocked. Every state below was driven for real — no request was mocked — and the
last column says what proved it (page text or HTTP, never the file name). The PNGs viewed by eye are listed in `notes/06-design/opened.txt`; duplicates in
`notes/06-design/duplicates.txt`.

| file | url at capture | state | width | theme | sha256 | state confirmed by |
| --- | --- | --- | --- | --- | --- | --- |
| `current-round--feedback-confirmed--390--light.png` | `/leagues/the-coupon/predictions` | confirmed | 390 | light | `457634c2c47e` | Carol: real POST → 201; toast “Grabbed Yes @ 1.95” type=success; title contrast 16.87:1 (feedback-run-1.txt) |
| `current-round--feedback-conflict--390--light.png` | `/leagues/the-coupon/predictions` | conflict | 390 | light | `1c407d35d834` | Alice: Bob claimed Brechin City over the API (201) after her card loaded; her POST → 409 SELECTION_TAKEN; toast type=warning, action “Refresh the card”; title contrast 17.31:1 |
| `current-round--feedback-price-moved--390--light.png` | `/leagues/the-coupon/predictions` | price-moved | 390 | light | `cbddc5dff4bd` | Hana: fake price moved 4.30 → 4.60 after her card loaded; POST → 409 PRICE_MOVED:4.60; toast type=warning, action “Take 4.60”; title contrast 17.31:1 |
| `current-round--feedback-queued-offline--390--light.png` | `/leagues/the-coupon/predictions` | queued-offline (no message shown — DES finding) | 390 | light | `8390179594e9` | Ivan: context offline, tapped Forfar Athletic; POSTs sent while offline: 0; toast after 5 s: none; outstanding notice: none |
| `current-round--feedback-queued-reconnected--390--light.png` | `/leagues/the-coupon/predictions` | queued pick sent on reconnect | 390 | light | `c53ab4df8214` | Ivan: back online; POST 201; toast “Grabbed Forfar Athletic @ 2.40” (success) |
| `current-round--feedback-confirmed--390--dark.png` | `/leagues/the-coupon/predictions` | confirmed | 390 | dark | `e7f7b9c82a4c` | Carol: real POST → 201 {"id":"541926ff-a2ae-4733-9ea6-99caf; toast “Grabbed Yes @ 1.95” type=success; title contrast 1.04:1 |
| `current-round--feedback-conflict--390--dark.png` | `/leagues/the-coupon/predictions` | conflict | 390 | dark | `2d93297ae463` | Alice: real POST → 409 {"detail":"SELECTION_TAKEN"}; toast “Someone in your league just grabbed that selection — pick another.” type=warning, action “Refresh the card”; title contrast 1.07:1 |
| `current-round--feedback-price-moved--390--dark.png` | `/leagues/the-coupon/predictions` | price-moved | 390 | dark | `402a620f50d3` | Hana: real POST → 409 {"detail":"PRICE_MOVED:4.60"}; toast “That price moved before your pick landed — it’s now 4.60. Tap again to take it.” type=warning, action “Take 4.60”; title contrast 1.07:1 |
| `current-round--feedback-queued-offline--390--dark.png` | `/leagues/the-coupon/predictions` | queued-offline (no message shown — DES finding) | 390 | dark | `96273338930e` | Ivan: context offline, tapped Yes; POSTs sent while offline: 1; toast after 5 s: none; outstanding notice: none |
| `current-round--feedback-queued-reconnected--390--dark.png` | `/leagues/the-coupon/predictions` | queued pick sent on reconnect | 390 | dark | `332f8f258101` | Ivan: back online; POST 201; toast “Grabbed Yes @ 1.80” (success) |
| `current-round--feedback-confirmed--1280--light.png` | `/leagues/the-coupon/predictions` | confirmed | 1280 | light | `61357294bd95` | Carol: real POST → 201 {"id":"541926ff-a2ae-4733-9ea6-99caf; toast “Grabbed The Draw @ 3.20” type=success; title contrast 16.87:1 |
| `current-round--feedback-conflict--1280--light.png` | `/leagues/the-coupon/predictions` | conflict | 1280 | light | `cc61f7b39845` | Alice: real POST → 409 {"detail":"SELECTION_TAKEN"}; toast “Someone in your league just grabbed that selection — pick another.” type=warning, action “Refresh the card”; title contrast 17.31:1 |
| `current-round--feedback-price-moved--1280--light.png` | `/leagues/the-coupon/predictions` | price-moved | 1280 | light | `af744cc63a0d` | Hana: real POST → 409 {"detail":"PRICE_MOVED:4.70"}; toast “That price moved before your pick landed — it’s now 4.70. Tap again to take it.” type=warning, action “Take 4.70”; title contrast 17.31:1 |
| `current-round--feedback-queued-offline--1280--light.png` | `/leagues/the-coupon/predictions` | queued-offline (no message shown — DES finding) | 1280 | light | `13f70928fb8b` | Ivan: context offline, tapped Forfar Athletic; POSTs sent while offline: 1; toast after 5 s: none; outstanding notice: none |
| `current-round--feedback-queued-reconnected--1280--light.png` | `/leagues/the-coupon/predictions` | queued pick sent on reconnect | 1280 | light | `42cf737da30f` | Ivan: back online; POST 201; toast “Grabbed Forfar Athletic @ 2.40” (success) |
| `current-round--feedback-confirmed--1280--dark.png` | `/leagues/the-coupon/predictions` | confirmed | 1280 | dark | `34d416226c40` | Carol: real POST → 201 {"id":"541926ff-a2ae-4733-9ea6-99caf; toast “Grabbed Yes @ 1.95” type=success; title contrast 1.04:1 |
| `current-round--feedback-conflict--1280--dark.png` | `/leagues/the-coupon/predictions` | conflict | 1280 | dark | `9d7ea2147692` | Alice: real POST → 409 {"detail":"SELECTION_TAKEN"}; toast “Someone in your league just grabbed that selection — pick another.” type=warning, action “Refresh the card”; title contrast 1.07:1 |
| `current-round--feedback-price-moved--1280--dark.png` | `/leagues/the-coupon/predictions` | price-moved | 1280 | dark | `8508bb27f590` | Hana: real POST → 409 {"detail":"PRICE_MOVED:4.80"}; toast “That price moved before your pick landed — it’s now 4.80. Tap again to take it.” type=warning, action “Take 4.80”; title contrast 1.07:1 |
| `current-round--feedback-queued-offline--1280--dark.png` | `/leagues/the-coupon/predictions` | queued-offline (no message shown — DES finding) | 1280 | dark | `dc10f8479f67` | Ivan: context offline, tapped Yes; POSTs sent while offline: 1; toast after 5 s: none; outstanding notice: none |
| `current-round--feedback-queued-reconnected--1280--dark.png` | `/leagues/the-coupon/predictions` | queued pick sent on reconnect | 1280 | dark | `c2009820c393` | Ivan: back online; POST 201; toast “Grabbed Yes @ 1.80” (success) |
| `current-round--feedback-busy--390--light.png` | `/leagues/the-coupon/predictions` | busy (PICKS_BUSY) | 390 | light | `a6800d4c3d7b` | Ivan: league budget exhausted by real submissions from Jo, Kai, Lee (the 23rd in busy-run.txt drew PICKS_BUSY); his POST → 429 PICKS_BUSY; toast type=error, no action; title contrast 16.08:1 |
| `current-round--feedback-busy--390--dark.png` | `/leagues/the-coupon/predictions` | busy (PICKS_BUSY) | 390 | dark | `6d9c86b89b06` | Ivan: league budget exhausted by real submissions from Jo, Kai, Lee (the 23rd in busy-run.txt drew PICKS_BUSY); his POST → 429 PICKS_BUSY; toast type=error, no action; title contrast 1.01:1 |
| `current-round--feedback-busy--1280--light.png` | `/leagues/the-coupon/predictions` | busy (PICKS_BUSY) | 1280 | light | `c89fbc352d42` | Ivan: league budget exhausted by real submissions from Jo, Kai, Lee (the 23rd in busy-run.txt drew PICKS_BUSY); his POST → 429 PICKS_BUSY; toast type=error, no action; title contrast 16.08:1 |
| `current-round--feedback-busy--1280--dark.png` | `/leagues/the-coupon/predictions` | busy (PICKS_BUSY) | 1280 | dark | `d250ee60838e` | Ivan: league budget exhausted by real submissions from Jo, Kai, Lee (the 23rd in busy-run.txt drew PICKS_BUSY); his POST → 429 PICKS_BUSY; toast type=error, no action; title contrast 1.01:1 |
| `current-round--settled-winner--390--light.png` | `/leagues/the-coupon/predictions` | settled-winner | 390 | light | `7aef0c4aedbe` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×1 |
| `current-round--settled-winner--390--dark.png` | `/leagues/the-coupon/predictions` | settled-winner | 390 | dark | `ce6d62af3f79` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×1 |
| `current-round--settled-winner--390--dark--full.png` | `/leagues/the-coupon/predictions` | settled-winner (full page) | 390 | dark | `c7958a9647a5` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×1 |
| `current-round--settled-winner--1280--light.png` | `/leagues/the-coupon/predictions` | settled-winner | 1280 | light | `6777aa9c66db` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×1 |
| `current-round--settled-winner--1280--light--full.png` | `/leagues/the-coupon/predictions` | settled-winner (full page) | 1280 | light | `162b8f8d5f54` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×1 |
| `current-round--settled-winner--1280--dark.png` | `/leagues/the-coupon/predictions` | settled-winner | 1280 | dark | `985ef2950b41` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×1 |
| `current-round--settled-void-leg--390--light.png` | `/leagues/the-coupon/predictions` | settled-void-leg | 390 | light | `4051c72253c0` | Ivan: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×1 |
| `current-round--settled-void-leg--390--dark.png` | `/leagues/the-coupon/predictions` | settled-void-leg | 390 | dark | `de7b6bd97b94` | Ivan: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×1 |
| `current-round--settled-void-leg--1280--light.png` | `/leagues/the-coupon/predictions` | settled-void-leg | 1280 | light | `5da96d7f616b` | Ivan: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×1 |
| `current-round--settled-void-leg--1280--dark.png` | `/leagues/the-coupon/predictions` | settled-void-leg | 1280 | dark | `184c6892e141` | Ivan: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×1 |
| `coupon--settled-void--390--light.png` | `/leagues/the-coupon/predictions/coupon` | settled-void | 390 | light | `7390efb254db` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×2, “Former member” present |
| `coupon--settled-void--390--dark.png` | `/leagues/the-coupon/predictions/coupon` | settled-void | 390 | dark | `4db1cbc45138` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×2, “Former member” present |
| `coupon--settled-void--390--dark--full.png` | `/leagues/the-coupon/predictions/coupon` | settled-void (full page) | 390 | dark | `0dfca4997cbb` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×2, “Former member” present |
| `coupon--settled-void--1280--light.png` | `/leagues/the-coupon/predictions/coupon` | settled-void | 1280 | light | `df92d5c9b900` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×2, “Former member” present |
| `coupon--settled-void--1280--light--full.png` | `/leagues/the-coupon/predictions/coupon` | settled-void (full page) | 1280 | light | `4070a6790256` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×2, “Former member” present |
| `coupon--settled-void--1280--dark.png` | `/leagues/the-coupon/predictions/coupon` | settled-void | 1280 | dark | `fc941dc67dcd` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “This week's coupon”, settled word yes, “void” ×2, “Former member” present |
| `results--settled--390--light.png` | `/leagues/the-coupon/predictions/results` | settled | 390 | light | `36407693cd1b` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “Season”, settled word yes, “void” ×0 |
| `results--settled--390--dark.png` | `/leagues/the-coupon/predictions/results` | settled | 390 | dark | `8531d21722b6` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “Season”, settled word yes, “void” ×0 |
| `results--settled--1280--light.png` | `/leagues/the-coupon/predictions/results` | settled | 1280 | light | `304d2f0d20fc` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “Season”, settled word yes, “void” ×0 |
| `results--settled--1280--dark.png` | `/leagues/the-coupon/predictions/results` | settled | 1280 | dark | `9e2336b0c926` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “Season”, settled word yes, “void” ×0 |
| `standings--settled-8-members--390--light.png` | `/leagues/the-coupon/leaderboard` | settled-8-members | 390 | light | `552ec984e447` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “The Coupon Test League”, settled word yes, “void” ×2, “Former member” present |
| `standings--settled-8-members--390--dark.png` | `/leagues/the-coupon/leaderboard` | settled-8-members | 390 | dark | `14f67fa0e5d0` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “The Coupon Test League”, settled word yes, “void” ×2, “Former member” present |
| `standings--settled-8-members--390--dark--full.png` | `/leagues/the-coupon/leaderboard` | settled-8-members (full page) | 390 | dark | `60d9c6353a80` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “The Coupon Test League”, settled word yes, “void” ×2, “Former member” present |
| `standings--settled-8-members--1280--light.png` | `/leagues/the-coupon/leaderboard` | settled-8-members | 1280 | light | `74a98eb6dbec` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “The Coupon Test League”, settled word yes, “void” ×2, “Former member” present |
| `standings--settled-8-members--1280--light--full.png` | `/leagues/the-coupon/leaderboard` | settled-8-members (full page) | 1280 | light | `897abebfaf6a` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “The Coupon Test League”, settled word yes, “void” ×2, “Former member” present |
| `standings--settled-8-members--1280--dark.png` | `/leagues/the-coupon/leaderboard` | settled-8-members | 1280 | dark | `b73536c0e370` | Alice: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “The Coupon Test League”, settled word yes, “void” ×2, “Former member” present |
| `home--after-settle-loser--390--light.png` | `/` | after-settle-loser | 390 | light | `28a60c4f5e5e` | Bob: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “Hi Bob”, settled word no, “void” ×0 |
| `home--after-settle-loser--390--dark.png` | `/` | after-settle-loser | 390 | dark | `53c700ce83b1` | Bob: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “Hi Bob”, settled word no, “void” ×0 |
| `home--after-settle-loser--1280--light.png` | `/` | after-settle-loser | 1280 | light | `78c20660cee2` | Bob: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “Hi Bob”, settled word no, “void” ×0 |
| `home--after-settle-loser--1280--dark.png` | `/` | after-settle-loser | 1280 | dark | `56e77dbb8f84` | Bob: round status `settled` via API (settle_design.py: 3 won, 1 void, 4 lost); page text: h1 “Hi Bob”, settled word no, “void” ×0 |
| `home--standalone-safearea--393--dark.png` | `/` | home — standalone + safe-area insets | 393 | dark | `ebd03bca8119` | Alice, iOS UA, standalone seen by the app (True), env(safe-area-inset) 59/34 via CDP: header 140px (pad 75px), tab bar 95px (pad 34px), theme-color #071A3D |
| `standings-toast--standalone-safearea--393--dark.png` | `/leagues/the-coupon/leaderboard` | standings-toast — standalone + safe-area insets | 393 | dark | `39d66ffb7e34` | Alice, iOS UA, standalone seen by the app (True), env(safe-area-inset) 59/34 via CDP: header 140px (pad 75px), tab bar 95px (pad 34px), theme-color #071A3D; toast “Standings copied” 15px above the tab bar |
| `current-round-offline--standalone-safearea--393--dark.png` | `/leagues/the-coupon/predictions` | current-round-offline — standalone + safe-area insets | 393 | dark | `6d294010d1ae` | Alice, iOS UA, standalone seen by the app (True), env(safe-area-inset) 59/34 via CDP: header 140px (pad 75px), tab bar 95px (pad 34px), theme-color #071A3D; offline banner top 140 (static) |
| `current-round-offline-scrolled--standalone-safearea--393--dark.png` | `/leagues/the-coupon/predictions` | current-round-offline-scrolled — standalone + safe-area insets | 393 | dark | `6b882b579852` | Alice, iOS UA, standalone seen by the app (True), env(safe-area-inset) 59/34 via CDP: header 140px (pad 75px), tab bar 95px (pad 34px), theme-color #071A3D; offline banner top -760 (static) |
| `home--standalone-safearea--393--light.png` | `/` | home — standalone + safe-area insets | 393 | light | `fa4ac3733ab5` | Alice, iOS UA, standalone seen by the app (True), env(safe-area-inset) 59/34 via CDP: header 140px (pad 75px), tab bar 95px (pad 34px), theme-color #F7F8FA |
| `standings-toast--standalone-safearea--393--light.png` | `/leagues/the-coupon/leaderboard` | standings-toast — standalone + safe-area insets | 393 | light | `8e264b8fd4d3` | Alice, iOS UA, standalone seen by the app (True), env(safe-area-inset) 59/34 via CDP: header 140px (pad 75px), tab bar 95px (pad 34px), theme-color #F7F8FA; toast “Standings copied” 15px above the tab bar |
| `current-round-offline--standalone-safearea--393--light.png` | `/leagues/the-coupon/predictions` | current-round-offline — standalone + safe-area insets | 393 | light | `0a013be47713` | Alice, iOS UA, standalone seen by the app (True), env(safe-area-inset) 59/34 via CDP: header 140px (pad 75px), tab bar 95px (pad 34px), theme-color #F7F8FA; offline banner top 140 (static) |
| `current-round-offline-scrolled--standalone-safearea--393--light.png` | `/leagues/the-coupon/predictions` | current-round-offline-scrolled — standalone + safe-area insets | 393 | light | `32fe6a56c392` | Alice, iOS UA, standalone seen by the app (True), env(safe-area-inset) 59/34 via CDP: header 140px (pad 75px), tab bar 95px (pad 34px), theme-color #F7F8FA; offline banner top -760 (static) |
| `my-leagues--happy-l06--390--light.png` | `/leagues` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | light | `18ad014b387f` | Alice: navigator.onLine=true, no offline banner, h1 “My Leagues”, 341 chars of page text |
| `my-leagues--happy-l06--390--dark.png` | `/leagues` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | dark | `aea774a079d2` | Alice: navigator.onLine=true, no offline banner, h1 “My Leagues”, 341 chars of page text |
| `my-leagues--happy-l06--1280--light.png` | `/leagues` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | light | `8b79733281de` | Alice: navigator.onLine=true, no offline banner, h1 “My Leagues”, 341 chars of page text |
| `my-leagues--happy-l06--1280--dark.png` | `/leagues` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | dark | `c9ccc0ae3bcb` | Alice: navigator.onLine=true, no offline banner, h1 “My Leagues”, 341 chars of page text |
| `my-leagues--firstrun-l06--390--light.png` | `/leagues` | firstrun (re-capture: lens 03’s copy shows the offline banner) | 390 | light | `5e91127c5a9e` | Dave: navigator.onLine=true, no offline banner, h1 “My Leagues”, 167 chars of page text |
| `my-leagues--firstrun-l06--390--dark.png` | `/leagues` | firstrun (re-capture: lens 03’s copy shows the offline banner) | 390 | dark | `7713c6b440de` | Dave: navigator.onLine=true, no offline banner, h1 “My Leagues”, 167 chars of page text |
| `my-leagues--firstrun-l06--1280--light.png` | `/leagues` | firstrun (re-capture: lens 03’s copy shows the offline banner) | 1280 | light | `30479e421f87` | Dave: navigator.onLine=true, no offline banner, h1 “My Leagues”, 167 chars of page text |
| `my-leagues--firstrun-l06--1280--dark.png` | `/leagues` | firstrun (re-capture: lens 03’s copy shows the offline banner) | 1280 | dark | `5da614c482b4` | Dave: navigator.onLine=true, no offline banner, h1 “My Leagues”, 167 chars of page text |
| `discover-leagues--happy-l06--390--light.png` | `/leagues/discover` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | light | `0da4ef2b1aaa` | Dave: navigator.onLine=true, no offline banner, h1 “Discover Leagues”, 144 chars of page text |
| `discover-leagues--happy-l06--390--dark.png` | `/leagues/discover` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | dark | `53676041ea98` | Dave: navigator.onLine=true, no offline banner, h1 “Discover Leagues”, 144 chars of page text |
| `discover-leagues--happy-l06--1280--light.png` | `/leagues/discover` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | light | `76c07842e4f1` | Dave: navigator.onLine=true, no offline banner, h1 “Discover Leagues”, 144 chars of page text |
| `discover-leagues--happy-l06--1280--dark.png` | `/leagues/discover` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | dark | `14e12f09b372` | Dave: navigator.onLine=true, no offline banner, h1 “Discover Leagues”, 144 chars of page text |
| `join-by-code--happy-l06--390--light.png` | `/leagues/join` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | light | `cd85bfd44722` | Dave: navigator.onLine=true, no offline banner, h1 “Join a league”, 124 chars of page text |
| `join-by-code--happy-l06--390--dark.png` | `/leagues/join` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | dark | `470a4b580743` | Dave: navigator.onLine=true, no offline banner, h1 “Join a league”, 124 chars of page text |
| `join-by-code--happy-l06--1280--light.png` | `/leagues/join` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | light | `162eda3ba636` | Dave: navigator.onLine=true, no offline banner, h1 “Join a league”, 124 chars of page text |
| `join-by-code--happy-l06--1280--dark.png` | `/leagues/join` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | dark | `1a30ea0772d5` | Dave: navigator.onLine=true, no offline banner, h1 “Join a league”, 124 chars of page text |
| `create-league--happy-l06--390--light.png` | `/leagues/new` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | light | `0f64e2bc552b` | Alice: navigator.onLine=true, no offline banner, h1 “Create a League”, 730 chars of page text |
| `create-league--happy-l06--390--dark.png` | `/leagues/new` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | dark | `8a4f80a9c62c` | Alice: navigator.onLine=true, no offline banner, h1 “Create a League”, 730 chars of page text |
| `create-league--happy-l06--1280--light.png` | `/leagues/new` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | light | `b52e7144c113` | Alice: navigator.onLine=true, no offline banner, h1 “Create a League”, 730 chars of page text |
| `create-league--happy-l06--1280--dark.png` | `/leagues/new` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | dark | `9d2397ed0237` | Alice: navigator.onLine=true, no offline banner, h1 “Create a League”, 730 chars of page text |
| `league-members--happy-l06--390--light.png` | `/leagues/the-coupon/admin/members` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | light | `2b9c1044d3a4` | Alice: navigator.onLine=true, no offline banner, h1 “Members”, 179 chars of page text |
| `league-members--happy-l06--390--dark.png` | `/leagues/the-coupon/admin/members` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | dark | `6f3339873506` | Alice: navigator.onLine=true, no offline banner, h1 “Members”, 179 chars of page text |
| `league-members--happy-l06--1280--light.png` | `/leagues/the-coupon/admin/members` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | light | `9c3252baa212` | Alice: navigator.onLine=true, no offline banner, h1 “Members”, 179 chars of page text |
| `league-members--happy-l06--1280--dark.png` | `/leagues/the-coupon/admin/members` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | dark | `d8a5223035bb` | Alice: navigator.onLine=true, no offline banner, h1 “Members”, 179 chars of page text |
| `league-settings--happy-l06--390--light.png` | `/leagues/the-coupon/admin/settings` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | light | `6fb8ad111cf6` | Alice: navigator.onLine=true, no offline banner, h1 “League Settings”, 1696 chars of page text |
| `league-settings--happy-l06--390--dark.png` | `/leagues/the-coupon/admin/settings` | happy (re-capture: lens 03’s copy shows the offline banner) | 390 | dark | `185701d26c75` | Alice: navigator.onLine=true, no offline banner, h1 “League Settings”, 1696 chars of page text |
| `league-settings--happy-l06--1280--light.png` | `/leagues/the-coupon/admin/settings` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | light | `26e0e4c03fa0` | Alice: navigator.onLine=true, no offline banner, h1 “League Settings”, 1696 chars of page text |
| `league-settings--happy-l06--1280--dark.png` | `/leagues/the-coupon/admin/settings` | happy (re-capture: lens 03’s copy shows the offline banner) | 1280 | dark | `33173c47eaa6` | Alice: navigator.onLine=true, no offline banner, h1 “League Settings”, 1696 chars of page text |
| `career-profile--settled-l06--390--light.png` | `/profile` | settled | 390 | light | `cf1b088f227f` | Hana: navigator.onLine=true, no offline banner, h1 “Hana”, 411 chars of page text |
| `career-profile--settled-l06--390--dark.png` | `/profile` | settled | 390 | dark | `950e40efa392` | Hana: navigator.onLine=true, no offline banner, h1 “Hana”, 411 chars of page text |
| `career-profile--settled-l06--1280--light.png` | `/profile` | settled | 1280 | light | `be41b5fbffe2` | Hana: navigator.onLine=true, no offline banner, h1 “Hana”, 411 chars of page text |
| `career-profile--settled-l06--1280--dark.png` | `/profile` | settled | 1280 | dark | `c80fb9395478` | Hana: navigator.onLine=true, no offline banner, h1 “Hana”, 411 chars of page text |
| `home--firstrun-l06--390--light.png` | `/` | firstrun | 390 | light | `ae2b788317ff` | Dave: navigator.onLine=true, no offline banner, h1 “Hi Dave”, 333 chars of page text |
| `home--firstrun-l06--390--dark.png` | `/` | firstrun | 390 | dark | `a84de570fca2` | Dave: navigator.onLine=true, no offline banner, h1 “Hi Dave”, 333 chars of page text |
| `home--firstrun-l06--390--dark--full.png` | `/` | firstrun (full page) | 390 | dark | `ca00186e6c35` | Dave: navigator.onLine=true, no offline banner, h1 “Hi Dave”, 333 chars of page text |
| `home--firstrun-l06--1280--light.png` | `/` | firstrun | 1280 | light | `335656449b41` | Dave: navigator.onLine=true, no offline banner, h1 “Hi Dave”, 333 chars of page text |
| `home--firstrun-l06--1280--dark.png` | `/` | firstrun | 1280 | dark | `28ed2c320d02` | Dave: navigator.onLine=true, no offline banner, h1 “Hi Dave”, 333 chars of page text |
<!-- lens-06 end -->

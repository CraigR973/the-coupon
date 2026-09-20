# Screenshot corpus index — `ux-capture`

172 PNGs, captured 2026-09-13/14 against the production bundle
(`vite build` + `vite preview --port 4103`) served from a seeded local API
(`uvicorn tests.e2e_server:app --port 8103`, migration 025, `ODDS_PROVIDER=fake`,
`FOOTBALL_DATA_PROVIDER=fake`). Chromium (Playwright), `deviceScaleFactor: 1`,
`reducedMotion: 'reduce'`. Theme forced via `localStorage.coupon_theme` set in
an `addInitScript` before first paint (verified: computed `body` background
light `rgb(247,248,250)`, dark `rgb(11,14,19)`). Auth forced the same way
(`coupon_access`/`coupon_refresh`/`coupon_player` in `localStorage`) — Alice is
league admin of `the-coupon` and promoted to site admin; Dave has no league.

Filename pattern: `<screen>--<state>--<390|1280>--<light|dark>[--full].png`.
`--full` is a full-page capture at 390 for screens that run well below the
fold (home, current round, results, standings). 1280 captures are the "happy"
state only, taken by a separate pass (`run-states.mjs` part 1) and do not have
an axe run against them — see `axe/` in the part dir for the 88 390px axe-core
4.10.2 runs this table's last column draws from (route sweep:
`<screen>--<theme>.json`; state variants: `state-<screen>-<state>-<theme>.json`).
"axe violations" is `<nodes>n/<rules>r: rule(impact letter), …` — `c`ritical,
`s`erious, `m`oderate, `mi`nor — or `0` where axe ran clean, or `—` where axe
was not run for that capture (1280 happy; `offline` and `pick-*` states, which
have no stable DOM state for axe to score against).

**Anomaly note**: `state-results-empty-dark.json` originally recorded 5
violations including `document-title` and `html-has-lang` on target `html`
and a `region` violation on target `pre` — i.e. the document never rendered
the app; something dumped raw text into a bare `<pre>` with no `<title>`/`lang`
set. Re-run 2026-09-14 against a freshly restarted stack (`title` "The
Coupon", `lang` "en", no `<pre>`, 0 axe violations, correct "No results yet"
empty-state copy in the DOM) confirms this was a capture-environment fault,
not a product defect — see `report.md` "Where this pass was wrong" for the
root cause. The table below and `results--empty--390--dark.png` reflect the
corrected re-run.

| file | route | state | viewport | theme | how produced | axe violations |
| --- | --- | --- | --- | --- | --- | --- |
| `about--happy--1280--dark.png` | `/about` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `about--happy--1280--light.png` | `/about` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `about--happy--390--dark.png` | `/about` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `about--happy--390--light.png` | `/about` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-calendar--happy--1280--dark.png` | `/admin/calendar` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-calendar--happy--1280--light.png` | `/admin/calendar` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-calendar--happy--390--dark.png` | `/admin/calendar` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-calendar--happy--390--light.png` | `/admin/calendar` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-dashboard--happy--1280--dark.png` | `/admin/dashboard` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-dashboard--happy--1280--light.png` | `/admin/dashboard` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-dashboard--happy--390--dark.png` | `/admin/dashboard` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-dashboard--happy--390--light.png` | `/admin/dashboard` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-invites--happy--1280--dark.png` | `/admin/invites` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-invites--happy--1280--light.png` | `/admin/invites` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-invites--happy--390--dark.png` | `/admin/invites` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-invites--happy--390--light.png` | `/admin/invites` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-leagues--happy--1280--dark.png` | `/admin/leagues` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-leagues--happy--1280--light.png` | `/admin/leagues` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-leagues--happy--390--dark.png` | `/admin/leagues` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-leagues--happy--390--light.png` | `/admin/leagues` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-players--happy--1280--dark.png` | `/admin/players` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-players--happy--1280--light.png` | `/admin/players` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-players--happy--390--dark.png` | `/admin/players` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-players--happy--390--light.png` | `/admin/players` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-results--happy--1280--dark.png` | `/admin/results` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-results--happy--1280--light.png` | `/admin/results` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-results--happy--390--dark.png` | `/admin/results` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-results--happy--390--light.png` | `/admin/results` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-sync--happy--1280--dark.png` | `/admin/sync` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-sync--happy--1280--light.png` | `/admin/sync` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `admin-sync--happy--390--dark.png` | `/admin/sync` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `admin-sync--happy--390--light.png` | `/admin/sync` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `career-profile--happy--1280--dark.png` | `/profile` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `career-profile--happy--1280--light.png` | `/profile` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `career-profile--happy--390--dark.png` | `/profile` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `career-profile--happy--390--light.png` | `/profile` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `create-league--happy--1280--dark.png` | `/leagues/new` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `create-league--happy--1280--light.png` | `/leagues/new` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `create-league--happy--390--dark.png` | `/leagues/new` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `create-league--happy--390--light.png` | `/leagues/new` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `current-round--error--390--dark.png` | `/leagues/the-coupon/predictions` | error | 390 | dark | Alice (league admin + site admin) — main query route fulfilled 500 `{"detail":"INTERNAL"}` | 0 |
| `current-round--error--390--light.png` | `/leagues/the-coupon/predictions` | error | 390 | light | Alice (league admin + site admin) — main query route fulfilled 500 `{"detail":"INTERNAL"}` | 0 |
| `current-round--happy--1280--dark.png` | `/leagues/the-coupon/predictions` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `current-round--happy--1280--light.png` | `/leagues/the-coupon/predictions` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `current-round--happy--390--dark--full.png` | `/leagues/the-coupon/predictions` | happy | 390 (full page) | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `current-round--happy--390--dark.png` | `/leagues/the-coupon/predictions` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `current-round--happy--390--light--full.png` | `/leagues/the-coupon/predictions` | happy | 390 (full page) | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `current-round--happy--390--light.png` | `/leagues/the-coupon/predictions` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `current-round--loading--390--dark.png` | `/leagues/the-coupon/predictions` | loading | 390 | dark | Alice (league admin + site admin) — main query route held open via `page.route` (never fulfilled) to capture skeleton/spinner; the script runs this same capture once against `/leagues/the-coupon/gameweek` and once against `/predictions`, so the file on disk is the second (predictions) run | 0 |
| `current-round--loading--390--light.png` | `/leagues/the-coupon/predictions` | loading | 390 | light | Alice (league admin + site admin) — main query route held open via `page.route` (never fulfilled) to capture skeleton/spinner; same duplicate-name note as above | 0 |
| `current-round--pick-busy--390--dark.png` | `/leagues/the-coupon/predictions` | pick-busy | 390 | dark | Alice (league admin + site admin) — POST `/picks` mocked 503 `PICKS_BUSY`; selection tapped | — (axe not run) |
| `current-round--pick-busy--390--light.png` | `/leagues/the-coupon/predictions` | pick-busy | 390 | light | Alice (league admin + site admin) — POST `/picks` mocked 503 `PICKS_BUSY`; selection tapped | — (axe not run) |
| `current-round--pick-confirm--390--dark.png` | `/leagues/the-coupon/predictions` | pick-confirm | 390 | dark | Alice (league admin + site admin) — POST `/picks` mocked 200 (pick confirmed); selection tapped | — (axe not run) |
| `current-round--pick-confirm--390--light.png` | `/leagues/the-coupon/predictions` | pick-confirm | 390 | light | Alice (league admin + site admin) — POST `/picks` mocked 200 (pick confirmed); selection tapped | — (axe not run) |
| `current-round--pick-conflict--390--dark.png` | `/leagues/the-coupon/predictions` | pick-conflict | 390 | dark | Alice (league admin + site admin) — POST `/picks` mocked 409 `SELECTION_TAKEN`; selection tapped | — (axe not run) |
| `current-round--pick-conflict--390--light.png` | `/leagues/the-coupon/predictions` | pick-conflict | 390 | light | Alice (league admin + site admin) — POST `/picks` mocked 409 `SELECTION_TAKEN`; selection tapped | — (axe not run) |
| `current-round--pick-pricemoved--390--dark.png` | `/leagues/the-coupon/predictions` | pick-pricemoved | 390 | dark | Alice (league admin + site admin) — POST `/picks` mocked 409 `PRICE_MOVED:3.25`; selection tapped | — (axe not run) |
| `current-round--pick-pricemoved--390--light.png` | `/leagues/the-coupon/predictions` | pick-pricemoved | 390 | light | Alice (league admin + site admin) — POST `/picks` mocked 409 `PRICE_MOVED:3.25`; selection tapped | — (axe not run) |
| `discover-leagues--happy--1280--dark.png` | `/leagues/discover` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `discover-leagues--happy--1280--light.png` | `/leagues/discover` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `discover-leagues--happy--390--dark.png` | `/leagues/discover` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `discover-leagues--happy--390--light.png` | `/leagues/discover` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `football--happy--1280--dark.png` | `/football` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `football--happy--1280--light.png` | `/football` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `football--happy--390--dark.png` | `/football` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `football--happy--390--light.png` | `/football` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `forgot-pin--happy--1280--dark.png` | `/forgot-pin` | happy | 1280 | dark | unauthenticated — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `forgot-pin--happy--1280--light.png` | `/forgot-pin` | happy | 1280 | light | unauthenticated — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `forgot-pin--happy--390--dark.png` | `/forgot-pin` | happy | 390 | dark | unauthenticated — seeded default data, session as noted, no mocking | 7n/3r: landmark-one-main(m), page-has-heading-one(m), region(m) |
| `forgot-pin--happy--390--light.png` | `/forgot-pin` | happy | 390 | light | unauthenticated — seeded default data, session as noted, no mocking | 7n/3r: landmark-one-main(m), page-has-heading-one(m), region(m) |
| `home--error--390--dark.png` | `/` | error | 390 | dark | Alice (league admin + site admin) — main query route fulfilled 500 `{"detail":"INTERNAL"}` | 0 |
| `home--error--390--light.png` | `/` | error | 390 | light | Alice (league admin + site admin) — main query route fulfilled 500 `{"detail":"INTERNAL"}` | 0 |
| `home--firstrun--390--dark.png` | `/` | firstrun | 390 | dark | Dave (no league) — new user, no league, default data | 0 |
| `home--firstrun--390--light.png` | `/` | firstrun | 390 | light | Dave (no league) — new user, no league, default data | 0 |
| `home--happy--1280--dark.png` | `/` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `home--happy--1280--light.png` | `/` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `home--happy--390--dark--full.png` | `/` | happy | 390 (full page) | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `home--happy--390--dark.png` | `/` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `home--happy--390--light--full.png` | `/` | happy | 390 (full page) | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `home--happy--390--light.png` | `/` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `home--loading--390--dark.png` | `/` | loading | 390 | dark | Alice (league admin + site admin) — main query routes (`gameweek/current`, `standings`) held open via `page.route` | 0 |
| `home--loading--390--light.png` | `/` | loading | 390 | light | Alice (league admin + site admin) — main query routes (`gameweek/current`, `standings`) held open via `page.route` | 0 |
| `home--offline--390--dark.png` | `/` | offline | 390 | dark | Alice (league admin + site admin) — loaded online, then `context.setOffline(true)` + a dispatched `offline` event | — (axe not run) |
| `home--offline--390--light.png` | `/` | offline | 390 | light | Alice (league admin + site admin) — loaded online, then `context.setOffline(true)` + a dispatched `offline` event | — (axe not run) |
| `join--happy--1280--dark.png` | `/join/:token` | happy | 1280 | dark | unauthenticated — seeded default data, sample invite token, no mocking | — (axe not run at 1280) |
| `join--happy--1280--light.png` | `/join/:token` | happy | 1280 | light | unauthenticated — seeded default data, sample invite token, no mocking | — (axe not run at 1280) |
| `join--happy--390--dark.png` | `/join/:token` | happy | 390 | dark | unauthenticated — seeded default data, sample invite token, no mocking | 3n/3r: landmark-one-main(m), page-has-heading-one(m), region(m) |
| `join--happy--390--light.png` | `/join/:token` | happy | 390 | light | unauthenticated — seeded default data, sample invite token, no mocking | 3n/3r: landmark-one-main(m), page-has-heading-one(m), region(m) |
| `join-by-code--happy--1280--dark.png` | `/leagues/join` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `join-by-code--happy--1280--light.png` | `/leagues/join` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `join-by-code--happy--390--dark.png` | `/leagues/join` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `join-by-code--happy--390--light.png` | `/leagues/join` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `league-audit-log--happy--1280--dark.png` | `/leagues/the-coupon/admin/audit-log` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `league-audit-log--happy--1280--light.png` | `/leagues/the-coupon/admin/audit-log` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `league-audit-log--happy--390--dark.png` | `/leagues/the-coupon/admin/audit-log` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `league-audit-log--happy--390--light.png` | `/leagues/the-coupon/admin/audit-log` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `league-invites--happy--1280--dark.png` | `/leagues/the-coupon/admin/invites` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `league-invites--happy--1280--light.png` | `/leagues/the-coupon/admin/invites` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `league-invites--happy--390--dark.png` | `/leagues/the-coupon/admin/invites` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `league-invites--happy--390--light.png` | `/leagues/the-coupon/admin/invites` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `league-members--happy--1280--dark.png` | `/leagues/the-coupon/admin/members` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `league-members--happy--1280--light.png` | `/leagues/the-coupon/admin/members` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `league-members--happy--390--dark.png` | `/leagues/the-coupon/admin/members` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `league-members--happy--390--light.png` | `/leagues/the-coupon/admin/members` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `league-requests--happy--1280--dark.png` | `/leagues/the-coupon/admin/requests` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `league-requests--happy--1280--light.png` | `/leagues/the-coupon/admin/requests` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `league-requests--happy--390--dark.png` | `/leagues/the-coupon/admin/requests` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `league-requests--happy--390--light.png` | `/leagues/the-coupon/admin/requests` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `league-settings--happy--1280--dark.png` | `/leagues/the-coupon/admin/settings` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `league-settings--happy--1280--light.png` | `/leagues/the-coupon/admin/settings` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `league-settings--happy--390--dark.png` | `/leagues/the-coupon/admin/settings` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `league-settings--happy--390--light.png` | `/leagues/the-coupon/admin/settings` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `login--happy--1280--dark.png` | `/login` | happy | 1280 | dark | unauthenticated — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `login--happy--1280--light.png` | `/login` | happy | 1280 | light | unauthenticated — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `login--happy--390--dark.png` | `/login` | happy | 390 | dark | unauthenticated — seeded default data, session as noted, no mocking | 0 |
| `login--happy--390--light.png` | `/login` | happy | 390 | light | unauthenticated — seeded default data, session as noted, no mocking | 0 |
| `my-leagues--firstrun--390--dark.png` | `/leagues` | firstrun | 390 | dark | Dave (no league) — new user, no league, default data | 0 |
| `my-leagues--firstrun--390--light.png` | `/leagues` | firstrun | 390 | light | Dave (no league) — new user, no league, default data | 0 |
| `my-leagues--happy--1280--dark.png` | `/leagues` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `my-leagues--happy--1280--light.png` | `/leagues` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `my-leagues--happy--390--dark.png` | `/leagues` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `my-leagues--happy--390--light.png` | `/leagues` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `offline-route--happy--1280--dark.png` | `/offline` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `offline-route--happy--1280--light.png` | `/offline` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `offline-route--happy--390--dark.png` | `/offline` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `offline-route--happy--390--light.png` | `/offline` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `player-profile--happy--1280--dark.png` | `/leagues/the-coupon/players/:id` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `player-profile--happy--1280--light.png` | `/leagues/the-coupon/players/:id` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `player-profile--happy--390--dark.png` | `/leagues/the-coupon/players/:id` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `player-profile--happy--390--light.png` | `/leagues/the-coupon/players/:id` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `register--happy--1280--dark.png` | `/register` | happy | 1280 | dark | unauthenticated — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `register--happy--1280--light.png` | `/register` | happy | 1280 | light | unauthenticated — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `register--happy--390--dark.png` | `/register` | happy | 390 | dark | unauthenticated — seeded default data, session as noted, no mocking | 0 |
| `register--happy--390--light.png` | `/register` | happy | 390 | light | unauthenticated — seeded default data, session as noted, no mocking | 0 |
| `results--empty--390--dark.png` | `/leagues/the-coupon/predictions/results` | empty | 390 | dark | Alice (league admin + site admin) — query route fulfilled 200 `[]`; re-captured 2026-09-14, see anomaly note above | 0 |
| `results--empty--390--light.png` | `/leagues/the-coupon/predictions/results` | empty | 390 | light | Alice (league admin + site admin) — query route fulfilled 200 `[]` | 0 |
| `results--happy--1280--dark.png` | `/leagues/the-coupon/predictions/results` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `results--happy--1280--light.png` | `/leagues/the-coupon/predictions/results` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `results--happy--390--dark--full.png` | `/leagues/the-coupon/predictions/results` | happy | 390 (full page) | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `results--happy--390--dark.png` | `/leagues/the-coupon/predictions/results` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `results--happy--390--light--full.png` | `/leagues/the-coupon/predictions/results` | happy | 390 (full page) | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `results--happy--390--light.png` | `/leagues/the-coupon/predictions/results` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `set-pin--happy--1280--dark.png` | `/set-pin` | happy | 1280 | dark | unauthenticated — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `set-pin--happy--1280--light.png` | `/set-pin` | happy | 1280 | light | unauthenticated — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `set-pin--happy--390--dark.png` | `/set-pin` | happy | 390 | dark | unauthenticated — seeded default data, session as noted, no mocking | 9n/3r: landmark-one-main(m), page-has-heading-one(m), region(m) |
| `set-pin--happy--390--light.png` | `/set-pin` | happy | 390 | light | unauthenticated — seeded default data, session as noted, no mocking | 9n/3r: landmark-one-main(m), page-has-heading-one(m), region(m) |
| `settings--happy--1280--dark.png` | `/settings` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `settings--happy--1280--light.png` | `/settings` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `settings--happy--390--dark.png` | `/settings` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `settings--happy--390--light.png` | `/settings` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `standings--archive--390--dark.png` | `/leagues/the-coupon/leaderboard` | archive | 390 | dark | Alice (league admin + site admin) — `**/seasons*` mocked to 2 seasons; navigated with `?season=2025` | 1n/1r: color-contrast(s) |
| `standings--archive--390--light.png` | `/leagues/the-coupon/leaderboard` | archive | 390 | light | Alice (league admin + site admin) — `**/seasons*` mocked to 2 seasons; navigated with `?season=2025` | 1n/1r: color-contrast(s) |
| `standings--empty--390--dark.png` | `/leagues/the-coupon/leaderboard` | empty | 390 | dark | Alice (league admin + site admin) — query route fulfilled 200 `[]` | 0 |
| `standings--empty--390--light.png` | `/leagues/the-coupon/leaderboard` | empty | 390 | light | Alice (league admin + site admin) — query route fulfilled 200 `[]` | 0 |
| `standings--error--390--dark.png` | `/leagues/the-coupon/leaderboard` | error | 390 | dark | Alice (league admin + site admin) — main query route fulfilled 500 `{"detail":"INTERNAL"}` | 0 |
| `standings--error--390--light.png` | `/leagues/the-coupon/leaderboard` | error | 390 | light | Alice (league admin + site admin) — main query route fulfilled 500 `{"detail":"INTERNAL"}` | 0 |
| `standings--happy--1280--dark.png` | `/leagues/the-coupon/leaderboard` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `standings--happy--1280--light.png` | `/leagues/the-coupon/leaderboard` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `standings--happy--390--dark--full.png` | `/leagues/the-coupon/leaderboard` | happy | 390 (full page) | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `standings--happy--390--dark.png` | `/leagues/the-coupon/leaderboard` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `standings--happy--390--light--full.png` | `/leagues/the-coupon/leaderboard` | happy | 390 (full page) | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `standings--happy--390--light.png` | `/leagues/the-coupon/leaderboard` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 0 |
| `standings--loading--390--dark.png` | `/leagues/the-coupon/leaderboard` | loading | 390 | dark | Alice (league admin + site admin) — main query route held open via `page.route` | 0 |
| `standings--loading--390--light.png` | `/leagues/the-coupon/leaderboard` | loading | 390 | light | Alice (league admin + site admin) — main query route held open via `page.route` | 0 |
| `team-season--happy--1280--dark.png` | `/football/teams/:id?competition=10932509&season=2025` | happy | 1280 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `team-season--happy--1280--light.png` | `/football/teams/:id?competition=10932509&season=2025` | happy | 1280 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `team-season--happy--390--dark.png` | `/football/teams/:id?competition=10932509&season=2025` | happy | 390 | dark | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 2n/1r: color-contrast(s) |
| `team-season--happy--390--light.png` | `/football/teams/:id?competition=10932509&season=2025` | happy | 390 | light | Alice (league admin + site admin) — seeded default data, session as noted, no mocking | 2n/1r: color-contrast(s) |
| `welcome--happy--1280--dark.png` | `/welcome` | happy | 1280 | dark | unauthenticated — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `welcome--happy--1280--light.png` | `/welcome` | happy | 1280 | light | unauthenticated — seeded default data, session as noted, no mocking | — (axe not run at 1280) |
| `welcome--happy--390--dark.png` | `/welcome` | happy | 390 | dark | unauthenticated — seeded default data, session as noted, no mocking | 2n/2r: landmark-one-main(m), region(m) |
| `welcome--happy--390--light.png` | `/welcome` | happy | 390 | light | unauthenticated — seeded default data, session as noted, no mocking | 2n/2r: landmark-one-main(m), region(m) |

Raw axe JSON (violations only, includes `data` for `color-contrast` where
re-checked) lives in the part dir, not this folder:
`.../scratchpad/parts/ux-capture/axe/`. `axe-summary.json` and
`states-summary.json` there give the per-run rollups this table was built from.

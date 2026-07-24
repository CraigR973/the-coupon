# Plan — Build "The Coupon" (app #3)

## Context

The next app: **The Coupon** — a private, invite-only weekly football *accumulator*
game for Craig + mates. Each "leaderboard" (a group) runs a weekly gameweek =
**one Saturday's 3pm kickoffs**. Every member makes **one pick** — a match +
market (**1X2** or **BTTS**) — and **no two members of a leaderboard may hold the
same selection** (first-come land-grab). Odds are **frozen at pick time**; picks
lock **14:30 Sat**; a winning pick scores **its odds × 10** (long shots reward
more); season = cumulative points. A **combined per-leaderboard accumulator** view
assembles everyone's picks into one acca to reference on a real book. Points/fun,
**no money**.

Every design decision was locked and evidence-backed this session (see memory
`project_the_coupon_planned`). Base and data source are settled:
- **Clone-and-own from calcio** (`wc_2026_predictor`) — the closest ancestor: it already
  has groups/leaderboards/memberships, football fixtures, and the auth+PWA shell.
  (Not app-starter, which would mean rebuilding all of that.)
- **Odds via the Betfair Exchange API** (free delayed key) — the only free source
  covering the **Scottish lower leagues**. Confirmed live: Betfair prices Match Odds
  **and** BTTS even for games like *Forfar v Brechin*. Scope = full English pyramid
  (PL/Champ/L1/L2) **+ full Scottish (Prem/Champ/L1/L2)**.

## Method

Clone calcio to a new sibling repo `the-coupon` (copy the working tree minus
`.git`/deps/caches, then fresh `git init` — clean history), and **squash to a new
baseline migration** rather than carry calcio's 40 World-Cup migrations. Same
proven approach as app-starter.

## Keep / Strip / Reshape

### Backend (`apps/api/src/`)
**KEEP (the crossover):** `auth.py`, `database.py`, `config.py`, `middleware.py`,
`rate_limit.py`, `logging_config.py`, `services/{backup,push_notification_service,notification_triggers}.py`;
models `base`, `profile`, `refresh_token`, `notification`, **`league`, `league_membership`,
`league_join_request`, `invite`**; routers `auth`, `health`, `me`, `notifications`,
**`leagues`, `league_memberships`, `league_join_requests`, `groups`, `leaderboard`**.
*(calcio's "league" = your "leaderboard" — terminology only.)*

**STRIP (World-Cup):** models `squad`, `survey`, and knockout bits; routers
`knockout_predictions`, `specials`, `squad`, `surveys`, `compare`, `players`, `stats`;
services `knockout_advancement`, `knockout_progression`, `football_data`, `result_sync`,
`email` (email signup → keep PIN/invite auth), `stats`, `storage`, `leaderboard` (the
trigger/merit-cascade scorer).

**RESHAPE (the mechanic):**
- `models/prediction.py` **→ `models/pick.py`**. calcio `Prediction` = (player_id, match_id,
  predicted score). New `Pick` = `(user_id, leaderboard_id, gameweek_id, fixture_id,
  market, outcome, odds_at_pick, betfair_market_id, betfair_selection_id, points_awarded,
  status)` with **two unique constraints**: `(leaderboard_id, gameweek_id, user_id)` — one
  pick each — and `(leaderboard_id, gameweek_id, fixture_id, market, outcome)` — no dupes.
- New `models/gameweek.py` (a Saturday: `kickoff_date`, `status` open→locked→settled,
  `locks_at` = 14:30) and `models/fixture.py` (match: home/away names, `kickoff_utc`,
  `competition`, Betfair event/market ids, result). `models/match.py` + `team.py` fold
  into these (Betfair gives team names directly — no separate Team table needed).
- **Scoring** (replaces `services/leaderboard.py` + the SQL trigger): new
  `services/scoring.py` — on settle, `points = round(odds_at_pick * 10)` if the pick's
  Betfair runner is `WINNER`, else 0; leaderboard = sum per member; rank by total, simple
  tiebreak. Reuse calcio's `leaderboard_snapshots` table shape for standings, fed from picks.
- New `services/coupon.py` — the combined-accumulator: a leaderboard+gameweek's picks →
  legs + combined odds (Π `odds_at_pick`).
- New `routers/{picks,coupon,gameweek}.py` (submit pick w/ unique enforcement + odds
  snapshot; combined acca; current slate). Registered in `main.py`.

### New: Betfair adapter (`services/betfair.py`) — replaces `football_data.py`
Uses calcio's `football_data.py` as the *structural* template (typed httpx client + retries),
new endpoints:
- **Auth:** interactive login (`identitysso.betfair.com/api/login`, username/pw → session
  token) + `keepAlive`; cert login is an optional later hardening step (interactive works —
  confirmed). Creds from env: `BF_APP_KEY`, `BF_USER`, `BF_PASS`.
- **Slate:** `listCompetitions` → resolve target league ids by name; `listEvents` filtered
  to **Saturday 15:00** → `Fixture`s / a `Gameweek`.
- **Odds:** `listMarketCatalogue` (`MATCH_ODDS`, `BOTH_TEAMS_TO_SCORE`) → selections;
  `listMarketBook` → back price for the snapshot. **Rule: only offer a selection Betfair
  prices** (handles thin lower-league BTTS gracefully).
- **Settlement:** `listMarketBook` after market `CLOSED` → runner `WINNER` → settle picks.
- **Mockable:** a `FakeBetfair` returning canned catalogues/books so the whole app is
  testable without a live login.

### Frontend (`apps/web/src/`)
**KEEP:** shell (`Layout`, `TopBar`, `TabBar`, `Brand`→rebrand, `PageHeader`,
`ProtectedRoute`, `PinInput`, `EmptyState`, PWA/notification controllers, `ui/`), all
league/group pages (`CreateLeague`, `DiscoverLeagues`, `Groups`, `GroupDetail`, `JoinByCode`,
`MyLeagues`, `LeagueMembers/Settings/Invites/JoinRequests`), `Leaderboard*` pages,
`lib/{api,tokens,leagues,leaderboard,utils,format,resumeRefetch}.ts`, hooks
`useCountdown` (the 14:30 lock), `useNow`, `usePushSubscription`, `useOnlineStatus`.
**STRIP:** `Bracket*`, `Knockout*`, `Specials*`, `Survey*`, `Week1*`, `CalcioLogo`,
`TournamentRevealModal`, `ComparePage`, `Signup/VerifyEmail` (email auth).
**RESHAPE:** `PredictionsPage`/`GroupPredictionsPage` **→ the weekly Coupon pick screen**
(this Saturday's slate; pick one selection; taken selections shown as unavailable; odds +
countdown to 14:30); `PredictionCard`→`PickCard`; `ScoringGuide`→odds rules; new
**CombinedAccaView**; `usePredictionEditor`→`usePickEditor`.

## Build order (batches)

1. **Scaffold + strip** — clone calcio → `the-coupon`, rebrand identifiers, delete WC
   backend+frontend modules, squash to a baseline migration (auth + leagues/memberships +
   gameweek + fixture + pick + leaderboard_snapshots). Backend compiles, ruff/mypy green.
2. **Betfair adapter** (`services/betfair.py` + `FakeBetfair`) — login/keepAlive, slate,
   odds, settlement; unit-tested against canned responses.
3. **Pick + scoring engine** — `Pick` model, unique constraints, submit endpoint (snapshot
   odds, enforce uniqueness), `services/scoring.py`, leaderboard standings, `services/coupon.py`.
4. **Scheduler** — jobs: refresh slate+odds (a few times pre-lock), lock at 14:30, settle
   Sat evening + recompute standings, pick reminder push.
5. **Frontend reshape** — Coupon pick screen, combined-acca view, rebrand; reuse league/leaderboard pages.
6. **Verify** (below) + rebrand pass (grep clean of calcio/WC/bracket/knockout).

## Verification

- **Backend:** `pytest` (Pick uniqueness both ways, odds-scoring math, combined-acca product,
  Betfair adapter against `FakeBetfair`, settlement), `ruff`, `mypy` — all green.
- **DB:** `alembic upgrade head` on a scratch Postgres (via `pgserver`, as used this session)
  → the baseline tables exist, no WC tables.
- **Frontend:** `pnpm --dir apps/web build` (Node 20) + `tsc` + vitest.
- **End-to-end (mocked Betfair, real Postgres, preview browser — the app-starter pattern):**
  seed a leaderboard + members → open the Saturday slate (from `FakeBetfair`) → two members
  pick; a third is blocked from a taken selection → lock → settle with canned results →
  leaderboard updates + combined-acca renders. Screenshot as proof.
- **Live Betfair check (Craig runs):** with his session token, confirm the real Saturday
  slate + odds populate (the coverage probe already proved lower-SPFL Match Odds + BTTS).

## Out of scope (gated)

- **No infra provisioning** in the build — its own fresh Supabase/Railway/Vercel comes at
  launch (per-app, per the app-starter runbook).
- **Betfair certificate (non-interactive) login** — optional hardening for the production
  server; interactive login is enough to build and run.
- **Live odds/coverage** depends on Craig's Betfair session (his money-linked account — the
  agent never logs in); the adapter is built + tested against `FakeBetfair` in the meantime.
- **App name/domain, real leagues, season kickoff** (lower divisions list markets from early
  August) — product/timing, not build blockers.

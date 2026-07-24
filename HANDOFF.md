# HANDOFF — building "The Coupon"

> **New session: read this first, then `docs/BUILD_PLAN.md`.** This repo is a
> **work-in-progress mid-Batch-1**. The backend does **not** compile yet (imports
> still reference stripped modules). Nothing is committed. Do not treat the
> inherited calcio docs (`README.md`, `session-log.md`, `wc2026-architecture.md`,
> and the current `AGENTS.md`) as accurate — they're leftovers to replace.

## What The Coupon is (one paragraph)

A private, invite-only **weekly football accumulator game** for Craig + mates.
Each "leaderboard" (a group) runs a weekly gameweek = **one Saturday's 3pm
kickoffs**. Every member makes **one pick** — a match + market (**1X2** or
**BTTS**) — and **no two members of a leaderboard may hold the same selection**
(first-come land-grab). Odds are **frozen at pick time**; picks lock **14:30
Sat**; a winning pick scores **its odds × 10** (long shots reward more); season =
cumulative points. A **combined per-leaderboard accumulator** view assembles
everyone's picks into one acca to reference on a real book. **Points/fun, no
money.** Full spec + keep/strip/reshape map + batch order: **`docs/BUILD_PLAN.md`**.

## Locked decisions (do NOT re-litigate — settled with evidence this session)

- **Base:** clone-and-own from **calcio** (`/Users/craigrobinson/wc_2026_predictor`) —
  its groups/leaderboards/memberships + PWA shell are the crossover. This repo IS
  that clone (`git init`'d, no calcio history, no secrets).
- **Auth:** **pure PIN + invite, no email** (admin creates accounts / invite links;
  name + 4-digit PIN sign-in). → **Port app-starter's already-built, verified auth
  spine** rather than untangle calcio's email-first auth (see next section).
- **Odds/data source:** **Betfair Exchange API** (free *delayed* app key), single
  source. It's the **only free source that covers the Scottish lower leagues**.
  Verified live this session: The Odds API doesn't carry lower SPFL; API-Football
  has zero odds for Scottish Champ/L2; Betfair prices Match Odds **and** BTTS even
  for *Forfar v Brechin*. Betfair data model: Events→Markets(`MATCH_ODDS`/
  `BOTH_TEAMS_TO_SCORE`)→Runners; settle via runner `WINNER`.
- **Scope:** English pyramid (PL/Champ/L1/L2) **+ full Scottish (Prem/Champ/L1/L2)**.
- **Rule that makes it robust:** *only offer a selection Betfair actually prices*
  (handles thin lower-league BTTS gracefully).

## Current state (what's done, what's broken)

**Done (Batch 1, partial):**
- Cloned calcio → this repo (no `.env`/secrets, fresh git init on `main`, 0 commits).
- Stripped ALL World-Cup backend modules:
  - models deleted: `group, team, match, squad, survey, prediction`
  - routers deleted: `admin, compare, groups, knockout_predictions, matches, players, predictions, specials, squad, stats, surveys, test_helpers, leaderboard`
  - services deleted: `email, football_data, knockout_advancement, knockout_progression, leaderboard, result_sync, stats, storage`
  - src root deleted: `reveal_gate, seed, seed_squads, data/`, `services/{notification_triggers,prediction_reminders}`
- **Remaining backend spine (KEEP):** models `base, profile, refresh_token, notification, league, league_membership, league_join_request, invite`; routers `auth, health, me, notifications, leagues, league_memberships, league_join_requests`; services `backup, push_notification_service`.

**Broken / NOT done — the tree does NOT compile:** the kept files still import
deleted modules. Key tangles found this session:
- calcio hid the **notification models** (`PushSubscription`, `NotificationPreferences`,
  `LeaderboardSnapshot`) *inside* the now-deleted `models/prediction.py`.
- calcio's **auth is email-first** (`auth.py` imports `services.email`, `services.storage`;
  signup/verify-email/avatar) — a real reshape, not just import fixes.
- `me.py` is the WC "my stats" page (imports Match/KnockoutPrediction/etc.).
- `main.py`, `models/__init__.py`, `scheduler.py`, `bootstrap_admin.py`,
  `push_notification_service.py`, `routers/notifications.py` all reference deleted modules.

## RESUME HERE — the next concrete steps

**Finish Batch 1 (get to a compiling spine):**
1. **Port app-starter's clean infra spine** from `/Users/craigrobinson/app-starter`
   (also on GitHub: `CraigR973/app-starter`, private template) — it's the *exact*
   PIN/invite model, already stripped + verified with a real-Postgres browser login.
   Bring over its `apps/api/src/`: `auth.py`, `activate.py`, `models/{profile,refresh_token,notification}.py`,
   `routers/{auth,me,notifications}.py`, `services/{push_notification_service,backup}.py`,
   plus the matching tests. These REPLACE calcio's tangled versions.
2. **Reconcile calcio's leagues to the ported spine** — the seams are small: calcio
   uses `CurrentPlayer` auth dep + `player_id` FK naming + a couple of `avatar_url`
   reads (`routers/leagues.py:532/590`, `routers/league_memberships.py:181`). Align
   the auth-dep name and Profile FK field; drop or stub `avatar_url`.
3. **Reduce `scheduler.py`** to the framework (app-starter has the pattern: `create_scheduler()`
   + `backup` + `connection_warmup`; domain jobs come in Batch 4).
4. **Rebuild `me.py`** as a minimal profile endpoint for now (the Coupon "my picks/points"
   version needs the Pick model → comes with Batch 3).
5. **Squash to a baseline migration** (like app-starter's `001_baseline`): profiles +
   refresh_tokens + notification tables + leagues + memberships + join_requests + invites.
   (Gameweek/fixture/pick tables get added in Batch 3.)
6. **Fix `main.py` router registration + `models/__init__.py`**, then get **compiling +
   `ruff`/`mypy` green**. Batch 1 done.

**Then Batches 2–6** (see `docs/BUILD_PLAN.md`): Betfair adapter (+ `FakeBetfair`
mock) → Pick model + odds scoring + combined-acca → scheduler jobs → frontend
reshape (Coupon pick screen + combined-acca) → verify end-to-end.

## Gotchas / environment (learned this session)

- **Web build/typecheck needs Node 20** (via nvm 20.20.2) + `pnpm`; `pnpm install` at
  repo root links the workspace.
- **Backend deps:** install with `--prefer-binary` (else `cryptography` builds from
  source and fails). `python3.12` at `~/.local/bin/python3.12`.
- **Scratch Postgres for tests/e2e:** local Homebrew postgres is broken (openssl
  formula bug); use the pip package **`pgserver`** (`pip install pgserver`) — it
  vendors a real Postgres. See app-starter's e2e verify approach.
- **`app-starter` is the reference** for every infra/verification pattern (auth,
  migration baseline, pgserver e2e, PWA shell). Reuse it heavily.
- **Betfair (Batch 2 live check):** the app needs `BF_APP_KEY`, `BF_USER`, `BF_PASS`
  in `.env` (gitignored). Craig has a **delayed** app key. **The agent must NOT log
  into Craig's Betfair account** (money-linked) — build/test against `FakeBetfair`;
  Craig runs the live coverage probe himself. Interactive login works (no cert needed).
  A read-only coverage probe already confirmed lower-SPFL Match Odds + BTTS.
- **Craig's API keys** (Betfair delayed key; a working The Odds API key covering the
  5 big leagues; an API-Football free key) exist but are **credentials — keep them
  out of the repo/memory**; they live only in `.env`.

## Housekeeping for the new session
- Replace inherited calcio docs (`AGENTS.md`/`CLAUDE.md` symlink, `README.md`,
  `session-log.md`, `wc2026-architecture.md`, `STATUS.md`) with Coupon versions as
  part of the rebrand (Batch 6). Delete `HANDOFF.md` once the build is on its feet.
- Nothing is committed yet — commit only when Craig asks.

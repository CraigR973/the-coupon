# World Cup 2026 Prediction League — Architecture & Technical Design Document

**Version 1.2 — Final | May 2026**

*A private, invite-only prediction league web application for the 2026 FIFA World Cup. Built as a Progressive Web App (PWA) for a group of up to 15 friends and family.*

---

## 1. Project Overview

The World Cup 2026 Prediction League is a private web application that lets a group of up to 15 players compete by predicting match scores across the entire 2026 FIFA World Cup — from the 72 group stage matches through to the Final. An admin manages the league, oversees the tournament, and intervenes when needed; results are fetched automatically from football-data.org. Players submit predictions before each match locks at kickoff, track their points on a live leaderboard, and compete across group stage, knockout rounds, and tournament specials.

**Primary Users:** One admin with full management rights, and up to 15 players with prediction and viewing access.

**Deployment:** Private, invite-only. Initially runs locally, with a clear path to cloud deployment. Built as a PWA with offline support and native push notifications.

### 1.1 Core Objectives

- Manage a complete 2026 World Cup prediction league with up to 15 players
- Support all 104 matches — 72 group stage + 32 knockout (R32 through Final)
- Lock individual match predictions automatically at kickoff time
- Score predictions in real time as results come in (2pts correct goals, 3pts correct result, 5pts exact score)
- Support tournament special predictions (winner, Golden Boot, top scoring team)
- Support round-by-round knockout bracket predictions with escalating points
- Display a live, real-time leaderboard with full points breakdown per player
- Provide group standings tables updating as results are entered
- Enable head-to-head prediction comparison between any two players
- Deliver rich player stats (accuracy %, average points, best/worst rounds)
- Send push notifications for result entries, deadline warnings, and leaderboard shifts
- Provide admin tools for result override, player management, and invite generation
- Automatically fetch match results from football-data.org every 5 minutes — no admin input required
- Trigger scoring, leaderboard updates, and push notifications automatically on result detection
- Allow admin to override any auto-fetched result with full audit trail
- Handle postponed, cancelled, and rescheduled matches gracefully
- Maintain a prediction audit trail (timestamps proving no backdating)
- Support a match schedule with dates, times, venues, and countdown timers
- Be installable as a PWA on mobile and desktop

### 1.2 Tournament Format

The 2026 FIFA World Cup uses an expanded 48-team format:

- **48 teams** across **12 groups** (A–L) of 4 teams each
- **Group stage:** Each team plays 3 matches (6 matches per group, 72 total)
- **Advancement:** Top 2 from each group (24 teams) + best 8 third-placed teams (8 teams) = 32 teams advance
- **Knockout rounds:** Round of 32 → Round of 16 → Quarter-Finals → Semi-Finals → Third Place Play-off → Final
- **Total matches:** 104 (72 group + 16 R32 + 8 R16 + 4 QF + 2 SF + 1 Third Place + 1 Final)
- **Tournament dates:** 11 June – 19 July 2026
- **Hosts:** USA, Canada, Mexico

---

## 2. Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | React 18 + Tailwind CSS + Vite | Fast dev experience, component-based UI, utility-first styling |
| PWA | Service Worker + Web App Manifest | Offline access, push notifications, installable on mobile/desktop |
| Backend / API | Python 3.12 + FastAPI | Async-first, auto-generated OpenAPI docs |
| Database | PostgreSQL (via Supabase) | Managed hosting, built-in auth, free tier, REST API, real-time subscriptions |
| DB Connection Pool | asyncpg + SQLAlchemy async | Connection pooling for FastAPI; default pool size 10, max overflow 10 |
| Full-Text Search | PostgreSQL tsvector + GIN index | Fast search across team names, player names, venues |
| Auth | Custom PIN-based (JWT, bcrypt) | Casual Name + PIN flow; no email required for players |
| Real-time | Supabase Realtime | Powers live leaderboard and result notification |
| Task Scheduling | APScheduler | Per-match kickoff lock jobs; result polling job; reschedule detection |
| Results API | football-data.org API (v4) | Free, official-quality football data — live scores, results, match status for all World Cup matches |
| Notifications | Web Push (pywebpush + VAPID keys) | Native push notifications on mobile and desktop via service worker |
| Component Library | shadcn/ui + Radix primitives | Premium, accessible, composable UI components on Tailwind |
| Icons | Lucide React | Consistent, well-designed icon set |
| Forms | React Hook Form + Zod | Type-safe validation, minimal re-renders |
| State Management | TanStack Query + Zustand | Server state (Query) and local UI state (Zustand) |
| Animation | Framer Motion | Smooth transitions, match card reveals, leaderboard shifts |
| Date/Time | date-fns + date-fns-tz | Lightweight, tree-shakeable, timezone-aware |
| Testing (Backend) | pytest + pytest-asyncio + httpx | Unit and integration tests with async support |
| Testing (Frontend) | Vitest + React Testing Library | Fast, Jest-compatible unit/component tests |
| E2E Testing | Playwright | Cross-browser end-to-end flow coverage |
| DB Migrations | Alembic | Version-controlled schema migrations for SQLAlchemy |
| Error Tracking | Sentry | Real-time error and performance monitoring |
| Logging | structlog | Structured JSON logging with context propagation |
| Rate Limiting | slowapi | FastAPI rate limiting on auth and abuse-prone endpoints |
| CI/CD | GitHub Actions | Automated tests, linting, type checking, deploys on every PR |
| Secrets | .env + Doppler (optional) | Environment variable management with `.env.example` for dev |

---

## 3. Data Model

All tables use UUID primary keys. Common conventions:

- **`created_at TIMESTAMP`** on every table (auto-set on insert via `NOW()`)
- **`updated_at TIMESTAMP`** on all mutable tables, auto-updated by Postgres trigger
- **`deleted_at TIMESTAMP NULL`** on critical tables (`profiles`, `predictions`, `matches`) for soft deletes — default queries filter `WHERE deleted_at IS NULL`

### 3.1 profiles

User accounts. Players authenticate with name + PIN; no email required.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| display_name | VARCHAR(100) | Shown in leaderboard and UI; UNIQUE constraint |
| pin_hash | VARCHAR(255) | Bcrypt-hashed PIN (4–8 digits, cost factor 12) |
| role | ENUM(admin, player) | Admin = full management; Player = predictions + read |
| avatar_color | VARCHAR(7) | Hex colour for player avatar (auto-assigned on join) |
| timezone | VARCHAR(50) | Player's IANA timezone (e.g. `Europe/London`); default `UTC` |
| failed_login_count | INTEGER | Increments on failed PIN; resets on success. Default 0 |
| locked_until | TIMESTAMP | NULL unless rate-limited; set after 5 failed attempts |
| is_active | BOOLEAN | False if admin has removed the player. Default true |
| joined_at | TIMESTAMP | When they accepted their invite |
| last_seen_at | TIMESTAMP | For "online now" indicators |
| created_at | TIMESTAMP | Auto-set |
| updated_at | TIMESTAMP | Auto-updated |

*Push subscriptions are stored separately in `push_subscriptions` (per-device). Notification preferences in `notification_preferences` (per-user).*

### 3.2 refresh_tokens

JWT refresh tokens, hashed before storage.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| player_id | UUID (FK → profiles) | Owner |
| token_hash | VARCHAR(64) | SHA-256 hash of the refresh token |
| device_hint | VARCHAR(100) | User agent hint (for "log out other devices" feature) |
| expires_at | TIMESTAMP | 30 days from issue |
| revoked_at | TIMESTAMP | Set on logout / admin revocation |
| created_at | TIMESTAMP | Auto-set |

### 3.3 invites

Admin-generated invite tokens for players to join the league.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| token | VARCHAR(64) (UNIQUE) | Random secure token embedded in the invite URL |
| display_name_hint | VARCHAR(100) | Optional: admin pre-fills the player's name |
| created_by | UUID (FK → profiles) | Admin who created it |
| claimed_by | UUID (FK → profiles) | Player who used it (null until claimed) |
| claimed_at | TIMESTAMP | When the invite was used |
| expires_at | TIMESTAMP | Optional expiry (default 7 days) |
| is_active | BOOLEAN | Admin can revoke before use. Default true |
| created_at | TIMESTAMP | When created |

*Invite URL format: `/join/{token}`. On visit, player sets their display name and PIN. Token is single-use.*

### 3.4 teams

All 48 teams in the 2026 World Cup. Seeded at application startup.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| name | VARCHAR(100) | e.g. "Brazil" |
| code | VARCHAR(3) | ISO 3166-1 alpha-3 country code e.g. "BRA" |
| flag_emoji | VARCHAR(10) | Emoji flag character(s) |
| group_id | UUID (FK → groups) | Which group they are in |
| eliminated_at_stage | ENUM(group, r32, r16, qf, sf, third_place, final, winner) | NULL until eliminated; `winner` = tournament winner |
| is_host | BOOLEAN | USA, Canada, Mexico |
| football_data_team_id | INTEGER | football-data.org team ID for API mapping |
| created_at | TIMESTAMP | Auto-set |

### 3.5 groups

The 12 groups (A–L).

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| name | VARCHAR(1) (UNIQUE) | "A" through "L" |
| created_at | TIMESTAMP | Auto-set |

### 3.6 matches

All 104 matches across all rounds. Group stage matches are seeded at startup; knockout matches are created by admin once advancement is determined.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| stage | ENUM(group, r32, r16, qf, sf, third_place, final) | Lowercase snake_case throughout |
| group_id | UUID (FK → groups) | NULL for knockout matches |
| match_number | INTEGER (UNIQUE) | Official FIFA match number (1–104) |
| home_team_id | UUID (FK → teams) | Home team (NULL for knockout until determined) |
| away_team_id | UUID (FK → teams) | Away team (NULL for knockout until determined) |
| home_team_placeholder | VARCHAR(50) | e.g. "Winner Group A" — shown before team is known |
| away_team_placeholder | VARCHAR(50) | e.g. "Runner-up Group B" |
| kickoff_utc | TIMESTAMP | Kickoff time in UTC; updated if FIFA reschedules |
| original_kickoff_utc | TIMESTAMP | Original scheduled kickoff (for audit when rescheduled) |
| venue | VARCHAR(255) | Stadium and city |
| status | ENUM(scheduled, locked, live, completed, postponed, cancelled) | See §6.13 for state machine |
| actual_home_score | INTEGER | NULL until result entered |
| actual_away_score | INTEGER | NULL until result entered |
| extra_time | BOOLEAN | Whether match went to extra time (knockout only). Default false |
| penalties | BOOLEAN | Whether match went to penalties (knockout only). Default false |
| penalty_winner_id | UUID (FK → teams) | Winner via penalties (knockout only) |
| result_source | ENUM(auto, manual, override) | How the result was entered: `auto` = fetched from API, `manual` = admin entered (no prior auto), `override` = admin corrected an auto result |
| football_data_match_id | INTEGER (UNIQUE) | football-data.org match ID for API mapping (set during seed) |
| last_synced_at | TIMESTAMP | When this match was last checked by the polling job |
| result_entered_at | TIMESTAMP | When result was first recorded (auto or manual) |
| result_entered_by | UUID (FK → profiles) | Which admin entered it (NULL if auto-fetched) |
| locked_at | TIMESTAMP | When predictions were locked (auto at kickoff) |
| postponed_reason | TEXT | Notes on postponement / cancellation if applicable |
| created_at | TIMESTAMP | Auto-set |
| updated_at | TIMESTAMP | Auto-updated |

*Indexes: `kickoff_utc` (scheduler queries), `(stage, status)` (filtering), `football_data_match_id` (API mapping).*

*APScheduler creates a lock job for every match at startup, keyed to `kickoff_utc`. When the job fires, `status` transitions from `scheduled` → `locked` and `locked_at` is set. If `kickoff_utc` is later updated, the lock job is re-registered (see §6.13).*

### 3.7 predictions

One row per player per match. Immutable after `match.status` transitions to `locked` or beyond.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| player_id | UUID (FK → profiles) | Who made the prediction |
| match_id | UUID (FK → matches) | Which match |
| predicted_home | INTEGER | Predicted home score (NULL = no prediction submitted) |
| predicted_away | INTEGER | Predicted away score (NULL = no prediction submitted) |
| submitted_at | TIMESTAMP | When first submitted (audit trail — proves no backdating) |
| update_count | INTEGER | Number of times the prediction was changed. Default 0 |
| points_awarded | INTEGER | NULL until result entered; calculated on result save. 0 if no prediction submitted |
| points_breakdown | JSONB | e.g. `{"goals": 2, "result": 3, "exact": 0, "total": 5, "no_prediction": false}` |
| created_at | TIMESTAMP | Auto-set |
| updated_at | TIMESTAMP | Auto-updated; serves as last-modified timestamp |

*Unique constraint on `(player_id, match_id)`. Points are calculated by a Postgres function triggered when `matches.actual_home_score` / `actual_away_score` are set. A player who never submitted a prediction (no row, or NULL scores) is awarded 0 points with `no_prediction: true` in the breakdown.*

### 3.8 knockout_predictions

Predictions for who will win each knockout match. Submitted round by round as teams are determined. **Each pick locks at its own match's kickoff** (per-match since U22.1 — a sibling tie kicking off no longer locks the rest of the round).

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| player_id | UUID (FK → profiles) | Who made the prediction |
| match_id | UUID (FK → matches) | The knockout match being predicted |
| predicted_winner_id | UUID (FK → teams) | Which team the player predicts to win |
| submitted_at | TIMESTAMP | Audit trail |
| update_count | INTEGER | Default 0 |
| points_awarded | INTEGER | NULL until result determined |
| created_at | TIMESTAMP | Auto-set |
| updated_at | TIMESTAMP | Auto-updated |

*Unique constraint on `(player_id, match_id)`. Points scale by round — see §6.1.*

### 3.9 special_predictions

Pre-tournament bonus predictions. All locked at the opening match kickoff.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| player_id | UUID (FK → profiles) | Who made the prediction |
| prediction_type | ENUM(tournament_winner, golden_boot, top_scoring_team, player_of_tournament, young_player_of_tournament, golden_glove) | Which special |
| predicted_team_id | UUID (FK → teams) | For tournament_winner and top_scoring_team |
| predicted_player_name | VARCHAR(100) | Display name for player specials |
| predicted_player_id | UUID (FK → squad_players) | For golden_boot, player_of_tournament, young_player_of_tournament, golden_glove |
| winner_player_id | UUID (FK → squad_players) | Stamped at award time for player specials |
| submitted_at | TIMESTAMP | Audit trail |
| points_awarded | INTEGER | NULL until tournament end |
| created_at | TIMESTAMP | Auto-set |
| updated_at | TIMESTAMP | Auto-updated |

*Unique constraint on `(player_id, prediction_type)`. Points: tournament_winner = 20, golden_boot = 15, top_scoring_team = 10, player_of_tournament = 15, young_player_of_tournament = 10, golden_glove = 10.*

### 3.10 leaderboard_snapshots

Point-in-time leaderboard records. Inserted after every result entry to power trend charts.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| player_id | UUID (FK → profiles) | Player |
| total_points | INTEGER | Total accumulated points at this moment |
| match_points | INTEGER | Points from group + knockout match score predictions |
| knockout_winner_points | INTEGER | Points from knockout winner predictions |
| special_points | INTEGER | Points from special predictions |
| rank | INTEGER | Position at this moment |
| snapshot_at | TIMESTAMP | When this snapshot was taken |
| triggered_by_match_id | UUID (FK → matches) | Which result triggered this snapshot |

*Index on `(snapshot_at, player_id)` for history chart queries.*

### 3.11 push_subscriptions

Per-device push subscriptions. A player may have multiple devices.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| player_id | UUID (FK → profiles) | Owner |
| subscription | JSONB | Web Push subscription object (endpoint, keys) |
| device_hint | VARCHAR(100) | User agent hint for display ("iPhone Safari") |
| failed_send_count | INTEGER | Increments on send failure. Default 0 |
| is_active | BOOLEAN | False if `failed_send_count >= 3`. Default true |
| created_at | TIMESTAMP | When registered |
| last_used_at | TIMESTAMP | When last successfully delivered |

### 3.12 notification_preferences

Per-player notification settings. One row per player, created on join with all categories enabled by default.

| Column | Type | Notes |
|---|---|---|
| player_id | UUID (PK, FK → profiles) | Owner — single row per player |
| deadline_warning | BOOLEAN | 1hr-before-kickoff reminder. Default true |
| match_locked | BOOLEAN | Confirmation when a match locks. Default true |
| result_detected | BOOLEAN | When a match result comes in. Default true |
| leaderboard_shift | BOOLEAN | When player's rank changes. Default true |
| round_complete | BOOLEAN | When a round ends. Default true |
| match_postponed | BOOLEAN | When a match is postponed/cancelled/rescheduled. Default true |
| special_results | BOOLEAN | Final special prediction results. Default true |
| global_mute | BOOLEAN | Master kill-switch. Default false |
| quiet_hours_start | TIME | No notifications during these hours. Default NULL |
| quiet_hours_end | TIME | Default NULL |
| created_at | TIMESTAMP | Auto-set |
| updated_at | TIMESTAMP | Auto-updated |

### 3.13 notification_log

Record of every push notification sent.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| player_id | UUID (FK → profiles) | Recipient |
| notification_type | ENUM | See list below |
| title | VARCHAR(255) | Notification title |
| body | TEXT | Notification body |
| match_id | UUID (FK → matches) | Related match (if applicable) |
| sent_at | TIMESTAMP | When sent |
| delivery_status | ENUM(sent, failed, expired, suppressed) | `suppressed` = preferences blocked it |

*`notification_type` ENUM values: `deadline_warning`, `match_locked`, `result_detected`, `leaderboard_shift`, `round_complete`, `match_postponed`, `kickoff_changed`, `invite_accepted`, `auto_sync_failed`, `special_results`.*

### 3.14 audit_log

Immutable log of all admin actions and significant system events.

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Internal identifier |
| actor_id | UUID (FK → profiles) | Who/what performed the action (NULL for system actions like auto-fetch) |
| actor_type | ENUM(admin, player, system) | `system` = automated job |
| action_type | ENUM | See list below |
| target_table | VARCHAR(50) | Which table was affected |
| target_id | UUID | Row ID affected |
| changes | JSONB | Diff of changes (old vs new values) |
| timestamp | TIMESTAMP | When it happened |

*`action_type` ENUM values: `result_auto_fetched`, `result_manual_entered`, `result_overridden`, `match_postponed`, `match_rescheduled`, `match_cancelled`, `kickoff_changed`, `predictions_locked`, `player_removed`, `player_pin_reset`, `invite_created`, `invite_revoked`, `knockout_advanced`, `special_awarded`, `sync_triggered`, `sync_failed`, `tiebreaker_overridden`.*

---

## 4. API Design

All endpoints are prefixed with **`/api/v1/`**. All endpoints return JSON with a consistent envelope:

```json
{
  "data": { ... },
  "meta": { "page": 1, "per_page": 20, "total": 104 },
  "errors": null
}
```

Error responses:

```json
{
  "data": null,
  "errors": [{ "code": "PREDICTION_LOCKED", "message": "This match has already kicked off.", "field": null }]
}
```

Authentication is via JWT Bearer tokens. Access tokens expire after 24 hours; refresh tokens after 30 days. A persisted browser/PWA session is PIN re-locked on reopen: protected routes do not mount until the player re-enters their PIN and `/auth/login` succeeds for the stored account. Rate limits apply to auth and abuse-prone paths.

### 4.1 Key Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| **Auth** | | | |
| POST | /api/v1/auth/join | Public | Join league with invite token — set name + PIN, receive JWT pair |
| POST | /api/v1/auth/login | Public | Login with name + PIN, receive JWT pair |
| POST | /api/v1/auth/refresh | Public | Exchange refresh token for new access token |
| POST | /api/v1/auth/logout | Any | Invalidate refresh token for current device |
| GET | /api/v1/auth/me | Any | Current player profile |
| PUT | /api/v1/auth/me/pin | Any | Change own PIN (requires current PIN) |
| POST | /api/v1/admin/players/{id}/reset-pin | Admin | Reset a player's PIN (returns temporary PIN to admin) |
| **Invites** | | | |
| POST | /api/v1/admin/invites | Admin | Create a new invite link (with optional name hint + expiry) |
| GET | /api/v1/admin/invites | Admin | List all invites (claimed, pending, expired) |
| DELETE | /api/v1/admin/invites/{id} | Admin | Revoke an unclaimed invite |
| **Players** | | | |
| GET | /api/v1/players | Any | List all active players (name, avatar, joined date) |
| GET | /api/v1/players/{id} | Any | Player profile with stats summary |
| DELETE | /api/v1/admin/players/{id} | Admin | Soft-remove a player from the league |
| **Matches** | | | |
| GET | /api/v1/matches | Any | All matches with status, teams, kickoff times, scores |
| GET | /api/v1/matches/{id} | Any | Single match detail with all player predictions (post-lock) |
| GET | /api/v1/matches/upcoming | Any | Next N matches ordered by kickoff |
| GET | /api/v1/matches/live | Any | Matches currently in progress |
| GET | /api/v1/matches/stage/{stage} | Any | All matches for a given stage |
| **Groups** | | | |
| GET | /api/v1/groups | Any | All 12 groups with current standings |
| GET | /api/v1/groups/{name} | Any | Single group (A–L) with standings + matches |
| **Results (Admin)** | | | |
| POST | /api/v1/admin/results/{match_id} | Admin | Manual result entry (fallback when auto-fetch unavailable) |
| PUT | /api/v1/admin/results/{match_id} | Admin | Override/correct a previously entered result |
| POST | /api/v1/admin/matches/{match_id}/lock | Admin | Manually lock a match early |
| POST | /api/v1/admin/matches/{match_id}/postpone | Admin | Mark match as postponed |
| PUT | /api/v1/admin/matches/{match_id}/reschedule | Admin | Update kickoff time and re-register lock job |
| POST | /api/v1/admin/matches/{match_id}/cancel | Admin | Mark match as cancelled (voids predictions) |
| POST | /api/v1/admin/knockout/advance | Admin | Set teams for a knockout match after previous round completes |
| POST | /api/v1/admin/groups/{name}/override-standings | Admin | Manually set group standings (tiebreaker edge cases) |
| **Predictions** | | | |
| GET | /api/v1/predictions/me | Any | All of the current player's predictions across all matches |
| PUT | /api/v1/predictions/{match_id} | Any | Submit or update a prediction (rejected if match locked) |
| GET | /api/v1/predictions/match/{match_id} | Any | All player predictions for a match (only visible post-lock) |
| GET | /api/v1/predictions/player/{player_id} | Any | All predictions for a specific player (post-lock only) |
| **Knockout Predictions** | | | |
| GET | /api/v1/knockout-predictions/me | Any | My knockout winner predictions |
| PUT | /api/v1/knockout-predictions/{match_id} | Any | Submit knockout winner prediction (rejected if round locked) |
| GET | /api/v1/knockout-predictions/match/{match_id} | Any | All players' knockout predictions (post-lock) |
| **Special Predictions** | | | |
| GET | /api/v1/specials | Any | All special prediction types + my current picks |
| PUT | /api/v1/specials/{type} | Any | Submit/update special prediction (locked at tournament start) |
| GET | /api/v1/specials/all | Any | All players' special predictions (visible post-tournament-start) |
| POST | /api/v1/admin/specials/award | Admin | Award points for special predictions at tournament end |
| **Leaderboard** | | | |
| GET | /api/v1/leaderboard | Any | Full leaderboard with points breakdown per player |
| GET | /api/v1/leaderboard/history | Any | Leaderboard positions over time (from snapshots) |
| GET | /api/v1/leaderboard/round/{stage} | Any | Leaderboard filtered to points earned in a specific round |
| **Head-to-Head** | | | |
| GET | /api/v1/compare/{player_a_id}/{player_b_id} | Any | Side-by-side prediction comparison for all completed matches |
| **Stats** | | | |
| GET | /api/v1/stats/me | Any | My personal stats (accuracy %, avg points, streaks, best round) |
| GET | /api/v1/stats/{player_id} | Any | Another player's stats |
| GET | /api/v1/stats/league | Any | League-wide stats |
| **Notifications** | | | |
| POST | /api/v1/notifications/subscribe | Any | Register a Web Push subscription |
| DELETE | /api/v1/notifications/subscribe | Any | Unsubscribe current device |
| POST | /api/v1/notifications/test | Any | Send a test push to current device |
| GET | /api/v1/notifications/preferences | Any | Get notification preferences |
| PUT | /api/v1/notifications/preferences | Any | Update notification preferences |
| **Admin** | | | |
| GET | /api/v1/admin/audit | Admin | View full audit log |
| GET | /api/v1/admin/dashboard | Admin | Admin summary: pending overrides, upcoming locks, active players, last sync status |
| GET | /api/v1/admin/sync/status | Admin | Last sync time, next scheduled sync, any errors from last run |
| POST | /api/v1/admin/sync/trigger | Admin | Manually trigger an immediate result sync |
| POST | /api/v1/admin/backup | Admin | Trigger an on-demand database snapshot |
| GET | /api/v1/admin/backups | Admin | List available backups |
| **Health** | | | |
| GET | /api/v1/health | Public | Liveness check |
| GET | /api/v1/health/ready | Public | Readiness check (DB, scheduler, football-data.org reachability) |

---

## 5. External Integrations

### 5.1 football-data.org — Automatic Result Fetching

football-data.org provides free, reliable, official-quality football data including live scores, match status, and final results for all major competitions including the FIFA World Cup.

**API details:**
- Base URL: `https://api.football-data.org/v4/`
- Authentication: API key in `X-Auth-Token` header (free tier, self-serve registration)
- Rate limit: 10 requests/minute on free tier — well within requirements
- Competition code: `WC` for FIFA World Cup
- Key endpoint: `GET /v4/competitions/WC/matches`

**Polling job (APScheduler — IntervalTrigger every 5 minutes):**

1. Job fires every 5 minutes throughout the tournament window (11 Jun – 19 Jul 2026)
2. Fetches all matches from football-data.org for the World Cup (no status filter — we need to detect status changes)
3. For each match, takes action based on the API status:
   - `SCHEDULED` → check if `kickoff_utc` matches; if not, trigger reschedule flow (§6.13)
   - `IN_PLAY` / `PAUSED` → set internal `matches.status = live`
   - `FINISHED` → enter result if not already present (auto), or update if existing auto result has changed
   - `POSTPONED` → set internal `matches.status = postponed`, log to audit, push notification
   - `CANCELLED` → set internal `matches.status = cancelled`, void predictions, log to audit
4. For every newly entered result: trigger scoring pipeline, insert `leaderboard_snapshots`, broadcast via Supabase Realtime, queue push notifications
5. Update `matches.last_synced_at` for all checked matches
6. Sync run summary stored in an in-memory status object for the admin dashboard

**Auto vs manual precedence:**
- `result_source = auto` → can be updated by future auto fetches if API corrects the score
- `result_source = manual` → admin entered manually before auto-fetch caught it; auto-fetch will not overwrite
- `result_source = override` → admin overrode an auto result; auto-fetch will not overwrite

**Admin override:**
If the API returns an incorrect result, admin can override via the result entry form. Overridden results are marked `result_source = override` and never touched by auto-sync again.

**Concurrency / race condition handling:**
The auto-fetch job and admin manual-entry both write to `matches` under a row-level lock (`SELECT ... FOR UPDATE`). The first to acquire wins; the second sees the updated state and either skips (auto) or proceeds as an override (admin). The admin UI surfaces a warning if the result has changed since the form was opened.

**Failure handling:**
- API unreachable (timeout, 5xx): job logs error, increments `consecutive_failure_count`, skips
- After 3 consecutive failures: push notification to admin (`auto_sync_failed`)
- Admin can trigger a manual sync at any time via `POST /admin/sync/trigger`
- Admin can fall back to manual result entry — the form is always available

**API key management:**
- Key stored as `FOOTBALL_DATA_API_KEY` environment variable
- Free tier key from football-data.org — no cost, self-serve at football-data.org/client/register

---

## 6. Key Features Detail

### 6.1 Scoring System

Points are awarded per prediction automatically when a result is detected (auto or manual). Calculation is performed by a Postgres function triggered on result entry and stored in `predictions.points_awarded` with a full breakdown in `predictions.points_breakdown`.

**Group stage match scoring:**

| Criteria | Points |
|---|---|
| Correct combined total goals (e.g. predicted 2-1, actual 3-0: both = 3 goals) | 2 |
| Correct result (Win / Draw / Loss — ignoring score) | 3 |
| Exact scoreline (both goals correct) | 5 |
| **Maximum per group stage match** | **10** |

**No prediction submitted:** 0 points awarded with `no_prediction: true` in the breakdown. No row may exist, or the row may have NULL scores.

**Knockout match scoring (identical rules to group, applied to 90-minute result):**

Extra time and penalties determine advancement but do not affect score-based prediction points. A match that ends 1-1 after 90 minutes (then decided on penalties) is scored as a 1-1 draw for prediction purposes — a correctly predicted draw earns the full +3 result points. Knockout winner predictions (who advances) use a separate points system.

**Knockout winner predictions (per round):**

| Round | Matches | Points per correct winner | Round max |
|---|---|---|---|
| Round of 32 | 16 | 5 | 80 |
| Round of 16 | 8 | 10 | 80 |
| Quarter-Finals | 4 | 15 | 60 |
| Semi-Finals | 2 | 20 | 40 |
| Third Place Play-off | 1 | 10 | 10 |
| Final | 1 | 25 | 25 |
| **Total knockout winner picks** | **32** | | **295** |

**Special predictions (awarded at tournament end):**

| Prediction | Points |
|---|---|
| Tournament Winner (pre-tournament) | 20 |
| Golden Boot (top scorer) | 15 |
| Player of the Tournament (Golden Ball) | 15 |
| Top Scoring Team | 10 |
| Young Player of the Tournament | 10 |
| Golden Glove (best goalkeeper) | 10 |
| **Total specials** | **80** |

**Maximum possible points (theoretical):**
- Group stage: 72 matches × 10pts = **720**
- Knockout matches (score predictions): 32 matches × 10pts = **320**
- Knockout winner predictions: **295**
- Special predictions: **80**
- **Grand total: ≈1,415 points**

### 6.2 Per-Match Prediction Locking

Predictions lock automatically at each match's kickoff time. This is more fair than a single tournament-wide lock and maintains engagement throughout the six-week tournament.

**Lock flow:**
1. At application startup, APScheduler registers a `DateTrigger` lock job for every scheduled match keyed to `kickoff_utc`
2. When the job fires: `matches.status` → `locked`, `locked_at` is set
3. Any PUT to `/api/v1/predictions/{match_id}` after lock returns a `PREDICTION_LOCKED` error
4. Players who haven't predicted that match receive a `deadline_warning` push 1 hour before kickoff
5. Admin can manually lock a match early (e.g. if a game is moved up) via `POST /admin/matches/{id}/lock`

**Knockout locking (per-match since U22.1):**
- Each knockout prediction locks at its own match's kickoff — siblings in the same round are independent
- e.g. one R32 match kicking off no longer locks the other R32 predictions

**Special predictions:**
- All special predictions lock at the kickoff of the opening match of the tournament

### 6.3 Group Standings

Live group standings are calculated dynamically from completed match results using FIFA tiebreaker rules:

1. Points (W=3, D=1, L=0)
2. Goal difference
3. Goals scored
4. Head-to-head points
5. Head-to-head goal difference
6. Head-to-head goals scored
7. Admin override (used as a manual tiebreaker for edge cases beyond the above — e.g. drawing of lots)

Standings displayed per group on the Groups page and as a compact widget on match cards. Admin override via `POST /admin/groups/{name}/override-standings` lets the admin pin team positions when automated tiebreakers can't resolve.

### 6.4 Knockout Bracket

The knockout bracket is built progressively as each round completes:

1. After group stage: admin reviews the 8 best third-placed teams, confirms the 32 advancing teams, and sets R32 matchups (following FIFA's predetermined bracket structure)
2. The app generates R32 match records via `POST /admin/knockout/advance`. Kickoff times are pulled from football-data.org during creation and admin confirms before saving
3. Players submit R32 winner predictions before the first R32 match kicks off
4. After R32: when all R32 matches have results, admin advances to R16 (same flow)
5. This process repeats through to the Final and Third Place Play-off

The bracket is displayed as an interactive visual tree showing all rounds from R32 to Final, with each player's predicted winner shown on their personal bracket view.

### 6.5 Special Predictions

Six pre-tournament predictions available to all players, submitted and locked before the opening match:

- **Tournament Winner** (20 pts) — which of the 48 teams wins the World Cup
- **Golden Boot** (15 pts) — which player scores the most goals
- **Player of the Tournament** (15 pts) — which player wins the Golden Ball award
- **Top Scoring Team** (10 pts) — which team scores the most goals across the tournament
- **Young Player of the Tournament** (10 pts) — which U21 player wins the Best Young Player award
- **Golden Glove** (10 pts) — which goalkeeper wins the best goalkeeper award (GK-only picker)

Player specials (Golden Boot, Player of the Tournament, Young Player, Golden Glove) use a squad player typeahead that resolves to `predicted_player_id`; the Golden Glove picker is filtered to GK position. All six are visible to all players after the tournament starts. Points are manually awarded by admin at tournament end via `POST /admin/specials/award`.

### 6.6 Live Leaderboard

The leaderboard updates in near-real-time using Supabase Realtime. When a result is auto-fetched (or entered manually by admin), points are recalculated server-side within a transaction and broadcast to all connected clients — no admin action required during the tournament.

**Leaderboard displays:**
- Rank (with change indicator vs previous snapshot: ↑2, ↓1, ─)
- Player name and avatar colour
- Total points
- Points from current round (badge)
- Predictions submitted count vs total possible
- Expandable row showing breakdown (match pts / knockout winner pts / special pts)

**Removed players:** Soft-deleted players (`is_active = false`) are excluded from the active leaderboard but their predictions and snapshots are preserved. Their head-to-head records remain visible historically. An admin-only toggle can show "All players including removed" for reference.

**Leaderboard history:**
A line chart showing each player's rank over time, plotted per match result. Powered by `leaderboard_snapshots` aggregated by `snapshot_at` timestamp.

**Round leaderboard:**
Filter leaderboard to show only points earned in a specific round.

### 6.7 Head-to-Head Comparison

Any player can compare their predictions against any other player's on all completed matches. The comparison shows:

- Side-by-side predicted scores for every completed match
- Actual result
- Points each player earned per match
- Win/draw/loss record between the two players (whoever earned more points per match)
- Who predicted more exact scores, more correct results, more correct goals

Available as a dedicated page and as a quick-comparison overlay accessible from the leaderboard. Removed players can still be selected for historical comparison.

### 6.8 Player Stats

A per-player statistics page showing:

- **Overall accuracy** — % of matches with at least a correct result prediction
- **Exact score rate** — % of predictions that were exact
- **Average points per match**
- **Best round** — which stage earned the most points
- **Worst round** — which stage was worst
- **Current streak** — consecutive correct results
- **Best day** — single match day with highest points
- **Prediction timing** — how far in advance predictions are typically submitted
- **Head-to-head record** vs every other player

### 6.9 Match Schedule & Countdown

A full match schedule page organised by date, showing:

- Match date, kickoff time (converted to each player's local timezone)
- Teams and flags (or placeholder text for knockout matches)
- Venue and city
- Match status pill (Upcoming / Locked / Live / Completed / Postponed / Cancelled)
- Countdown timer to kickoff for upcoming matches
- Player's own prediction shown inline (or a prompt to predict if not yet submitted)
- Actual result once entered

Filterable by group, stage, date range, and team. Upcoming matches prominently surface the "predict now" CTA.

**Timezone handling:** All `kickoff_utc` values are stored in UTC. The frontend converts to the player's `profiles.timezone` (default UTC) using `date-fns-tz` for display. Matches span US/Canada/Mexico time zones, so timezone display matters.

### 6.10 Admin Result Entry

With auto-fetch in place, the admin results page is primarily a monitoring and override interface:

- **Auto-fetch status banner** — last sync time, next scheduled sync, error state
- **Manual trigger** — "Sync now" button for immediate fetch
- **Pending list** — completed matches where auto-fetch has not yet detected a result (rare)
- **Manual entry fallback** — for delayed/incorrect API
- **Source badges** — every entered result tagged "Auto" / "Manual" / "Override"
- **Override flow** — confirmation step + audit log entry; recalculates all points
- **Concurrency guard** — if the result changed while admin had the form open, a warning is shown and admin must explicitly proceed

### 6.11 Invite System

Admin generates invite links from the Admin panel:

1. Admin optionally pre-fills the player's name and sets an expiry (default 7 days)
2. A unique 64-char token is generated: `https://app.domain.com/join/{token}`
3. Admin copies and shares the link (WhatsApp, text, email)
4. Player visits the link, confirms or sets their display name (must be unique), creates a PIN
5. Token is marked as claimed; `notification_preferences` row created with defaults; player can log in
6. Admin is notified via push when an invite is accepted

Admin can see all invites (pending, claimed, expired) and revoke unused ones. Maximum 15 active players enforced at claim time.

### 6.12 Push Notifications

Push notifications are delivered via Web Push (VAPID) through the service worker. Players must grant notification permission when they install the PWA.

**Notification types:** see `notification_log.notification_type` ENUM in §3.13.

**Preferences and quiet hours** stored in `notification_preferences` (§3.12). When a player has `global_mute = true` or it's within their quiet hours, the notification is logged with `delivery_status = suppressed` rather than sent.

**Delivery failures:** A push that fails 3 consecutive times causes `push_subscriptions.is_active = false`. The player is shown an "Re-enable notifications" banner on next visit.

### 6.13 Match State Machine & Reschedule Handling

`matches.status` follows this state machine:

```
scheduled ──(kickoff time reached)──▶ locked ──(API: IN_PLAY)──▶ live ──(API: FINISHED)──▶ completed
    │
    ├──(admin or API: POSTPONED)──▶ postponed ──(reschedule)──▶ scheduled
    │
    └──(admin or API: CANCELLED)──▶ cancelled (terminal)
```

**Postponed matches:**
- Predictions remain saved (not voided)
- Match removed from leaderboard scoring (no points awarded)
- Push notification (`match_postponed`) to all players
- When rescheduled, kickoff_utc is updated and a new lock job is registered (see below)

**Cancelled matches:**
- Predictions are voided (no points awarded, no scoring)
- Push notification (`match_postponed` with cancellation message) to all players
- Match shown with strikethrough on the schedule

**Reschedule flow (kickoff change):**
1. Detected by auto-fetch comparing API `utcDate` against internal `kickoff_utc`
2. `original_kickoff_utc` set (if not already), `kickoff_utc` updated
3. Existing APScheduler lock job is cancelled
4. New lock job registered against the updated `kickoff_utc`
5. Push notification (`kickoff_changed`) to all players who have predicted that match
6. Audit log entry (`kickoff_changed`)
7. If the new kickoff is in the past (rare), match is locked immediately

### 6.14 Prediction Audit Trail

Every prediction submission and update is timestamped:

- `predictions.submitted_at` — set on first save
- `predictions.updated_at` — auto-updated on every change (standard convention)
- `predictions.update_count` — increments on every change

The audit trail is visible to admin (showing each player's prediction history per match) and provides proof against any disputes about whether a prediction was entered before or after kickoff. The system enforces locking server-side — no prediction can be saved if `match.status` is anything other than `scheduled`.

### 6.15 Backup & Restore

**Automated backups:** Supabase performs a daily snapshot of the database on the free tier (kept for 7 days). On Pro tier, point-in-time recovery is available.

**On-demand backups:** Admin can trigger a manual backup via `POST /admin/backup`, which runs `pg_dump` and uploads the compressed archive to Supabase Storage. Retained for 30 days.

**Restore procedure (documented in `docs/runbooks/restore.md`):**
1. Admin downloads the most recent backup archive
2. Spin up a fresh Supabase project (or restore in-place if Pro tier)
3. Apply the archive via `psql`
4. Restart the backend — APScheduler will re-register all lock jobs from the restored data
5. Verify via the admin dashboard

**Pre-tournament:** A backup is taken automatically the night before the opening match.

**Mid-tournament backups:** Daily automatic backups are sufficient for casual use. For peace of mind, admin can trigger one before any major operation (knockout advancement, result override).

---

## 7. Frontend Architecture & Design System

### 7.1 Design Principles

The app should feel **energetic, modern, and football-forward** — not a generic SaaS dashboard. Think sports data apps, not spreadsheets.

**Inspirations:** UEFA/FIFA tournament apps for structure and data density; FotMob for real-time match feel; Sofascore for stats layout; FPL (Fantasy Premier League) for leaderboard psychology.

**Core tenets:**

- **Tournament-first** — the match schedule and leaderboard are the beating heart; everything else supports them
- **Glanceable** — players should see their standing and next match prediction at a glance from any page
- **Live-feeling** — result notifications, rank changes, and score updates should feel instant
- **Mobile-primary** — most players will check scores on their phone; desktop is a second-class citizen
- **Competitive energy** — leaderboard rank changes, point breakdowns, and streaks should feel rewarding

### 7.2 Design System

**Colour Palette**

| Token | Value | Usage |
|---|---|---|
| background | #0A0F1E | Page background (deep navy) |
| surface | #131929 | Cards, panels |
| surface-elevated | #1C2540 | Modals, dropdowns, hover states |
| border | #263354 | Dividers, card borders |
| text-primary | #F0F4FF | Headings, body |
| text-secondary | #8A9CC7 | Metadata, captions |
| text-muted | #4A5A80 | Placeholder, disabled |
| primary | #00E676 | Primary actions, CTAs, active states (electric green) |
| primary-dark | #00B854 | Primary hover |
| accent | #3D7FFF | Links, highlights, info states (bright blue) |
| gold | #FFD700 | 1st place, winner badges |
| silver | #C0C0C0 | 2nd place |
| bronze | #CD7F32 | 3rd place |
| success | #00E676 | Correct predictions, confirmations |
| warning | #FF9800 | Deadline warnings, attention |
| error | #FF4757 | Wrong predictions, errors |
| locked | #4A5A80 | Locked match indicator |
| live | #FF4757 | Live match pulsing indicator |

**Typography**

- **Display / Scores / Ranks:** Bebas Neue (bold, athletic, number-forward)
- **Headings / UI:** Outfit (clean, modern, excellent at all weights)
- **Mono / Timestamps:** JetBrains Mono (for kickoff times, scores)

**Motion**

- Leaderboard rank changes: animated position swap (300ms easeInOut)
- Points awarded: count-up animation on score reveal
- Match card lock: fade + blur transition
- Live indicator: pulsing red dot (CSS keyframes)
- Notification slide-in: from top, 250ms easeOut

### 7.3 Pages & Routes

| Page | Route | Description |
|---|---|---|
| Home / Dashboard | / | Live leaderboard summary, next match countdown, my latest points, recent results |
| Join League | /join/{token} | Invite claim — set name + PIN |
| Login | /login | Name + PIN login |
| Match Schedule | /schedule | Full fixture list by date, filterable by group/stage/team |
| My Predictions | /predictions | My prediction sheet across all matches, organised by group/round |
| Predictions — Group | /predictions/group/{name} | My predictions for a specific group (A–L) |
| Predictions — Knockout | /predictions/knockout | My knockout bracket predictions |
| Predictions — Specials | /predictions/specials | Tournament winner, Golden Boot, top scoring team |
| Leaderboard | /leaderboard | Full live leaderboard with breakdown |
| Leaderboard History | /leaderboard/history | Rank over time chart for all players |
| Round Leaderboard | /leaderboard/round/{stage} | Points earned in a specific round |
| Groups | /groups | All 12 group standings with match results |
| Group Detail | /groups/{name} | Single group — table, matches, team form |
| Bracket | /bracket | Visual knockout bracket tree |
| Head-to-Head | /compare | Select two players to compare predictions |
| Player Profile | /players/{id} | A player's stats, prediction history, head-to-heads |
| Match Detail | /matches/{id} | Single match — all predictions (post-lock), result, points breakdown |
| Admin — Dashboard | /admin | Sync status, pending overrides, upcoming locks, invite management |
| Admin — Results | /admin/results | Monitor auto-fetched results, override, manual entry fallback |
| Admin — Sync | /admin/sync | football-data.org sync status, manual trigger, error log |
| Admin — Knockout | /admin/knockout | Set knockout match teams as rounds advance |
| Admin — Players | /admin/players | Player list, remove player, reset PIN, view stats |
| Admin — Invites | /admin/invites | Create, view, revoke invite links |
| Admin — Backups | /admin/backups | Trigger and download database backups |
| Admin — Audit Log | /admin/audit | Full action history |
| Settings | /settings | PIN change, timezone, notification preferences, PWA install prompt |

### 7.4 Key Components

**Prediction Card:** Compact card per match showing home team, away team, two score inputs, lock status indicator, and points badge once result is in. Used on both /predictions and /schedule.

**Match Status Indicator:** Colour-coded pill — Upcoming (grey), Locked (orange padlock), Live (red pulse), Completed (green check), Postponed (amber dashed border), Cancelled (red strikethrough). Live status auto-updated by sync job.

**Leaderboard Row:** Rank number (Bebas Neue, coloured by medal), player name + avatar, total points (large), round points badge, trend arrow, expandable breakdown.

**Points Reveal:** When a result is detected (auto or manual), affected players' prediction cards animate to show earned points — count-up animation with colour-coded badge.

**Sync Status Widget:** Admin-only — shows last sync time, next sync countdown, and any error state.

**Bracket Tree:** Interactive SVG bracket showing all knockout rounds. Players' predictions overlaid in their avatar colour. Correct predictions highlighted in green after results.

**Countdown Timer:** Days/hours/minutes/seconds countdown to next match kickoff, respecting player's local timezone.

**Group Table:** Mini standings table per group — Team, P, W, D, L, GF, GA, GD, Pts. Updated live via Supabase Realtime.

### 7.5 State & Data Strategy

- **TanStack Query** manages all server state (caching, refetching, optimistic updates)
- **Zustand** for local UI state (modals, active filters, notification banners)
- **Supabase Realtime** subscriptions for live leaderboard and result updates
- **localStorage** for persistent user preferences and JWT tokens
- **Service Worker** for offline access to schedule and predictions

### 7.6 Mobile Gestures

- **Swipe left/right** on prediction cards to navigate between matches in a group
- **Pull to refresh** on leaderboard and schedule
- **Long press** on a player's leaderboard row to open head-to-head comparison
- **Haptic feedback** on prediction submission, result reveal, rank change

---

## 8. Authentication & Security

### 8.1 Authentication Flow

Players authenticate with a display name + 4–8 digit PIN. No email required.

**Token strategy:**
- **Access token:** JWT, 24-hour TTL, contains `player_id` and `role` claims, signed with HS256
- **Refresh token:** Opaque random string (32 bytes base64url), 30-day TTL, stored hashed (SHA-256) in `refresh_tokens` table
- Frontend stores both in `localStorage`; access token sent as Bearer header; refresh token used only against `POST /auth/refresh`
- 5 minutes before access token expiry, frontend silently calls `/auth/refresh` to get a new pair (refresh token rotated on every refresh)
- Reopening an installed app or browser tab with a stored session shows a PIN unlock gate before protected data renders; the gate posts the stored email + entered PIN to `/auth/login` and offers "not you? Log out" for shared devices
- `POST /auth/logout` invalidates the current refresh token

**Join flow (invite):**
1. Player visits `/join/{token}`
2. Token validated server-side (active, unclaimed, not expired)
3. Player confirms or sets display name (must be unique); creates a PIN
4. Server creates `profiles` row, marks invite as claimed, creates `notification_preferences` row, issues JWT pair
5. JWT pair stored in `localStorage`

**Login flow:**
1. Player selects their name from a dropdown
2. Enters PIN
3. Server bcrypt-compares PIN hash; issues JWT pair on match
4. Failed attempts increment `profiles.failed_login_count`
5. 5 failed attempts within 15 min → `locked_until` set 15 min in future; further attempts return `ACCOUNT_LOCKED`
6. Successful login resets `failed_login_count` to 0

**Admin auth:**
Admin is a designated profile created via a one-time bootstrap script at setup. Admin role is checked on every admin endpoint before processing. Admin cannot be removed via the normal player removal endpoint.

### 8.2 Prediction Visibility Rules

To prevent prediction peeking before matches lock:

- Predictions for a match are **only visible to other players after that match locks** (`status` ∈ `locked`, `live`, `completed`)
- The admin can always see all predictions (needed for dispute resolution)
- A player can always see their own predictions at any time
- Cancelled matches show predictions as voided

This is enforced at the API level — `GET /api/v1/predictions/match/{id}` checks `match.status` before returning other players' data.

### 8.3 Rate Limiting

| Endpoint | Limit |
|---|---|
| POST /auth/login | 5 attempts per 15 min per name+IP |
| POST /auth/join | 3 per hour per IP |
| POST /auth/refresh | 60 per hour per refresh token |
| PUT /auth/me/pin | 3 per hour per player |
| PUT /predictions/{match_id} | 60 per hour per player |
| PUT /knockout-predictions/{match_id} | 60 per hour per player |
| GET /leaderboard | 120 per minute per player (cached anyway) |
| POST /admin/sync/trigger | 10 per hour per admin |
| POST /admin/backup | 5 per day per admin |
| POST /notifications/test | 5 per hour per player |

### 8.4 Data Protection

- PIN never stored in plaintext — bcrypt with cost factor 12
- JWT access secret in `JWT_ACCESS_SECRET` env var; rotated annually
- Refresh tokens hashed (SHA-256) before storage
- CORS configured: `Access-Control-Allow-Origin` set to single frontend origin from `FRONTEND_ORIGIN` env var
- Security headers: HSTS, X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy strict-origin
- All admin actions logged to `audit_log` with diffs
- No PII beyond display names — no emails, no personal data
- football-data.org API key, Supabase service key, VAPID private key all environment-only

---

## 9. Reliability & Operations

### 9.1 Match Lock Scheduler

APScheduler manages the automatic prediction locking. On application startup:

1. All matches with `status = scheduled` are queried
2. A `DateTrigger` job is registered per match, firing at `kickoff_utc`
3. Job sets `match.status = locked`, `locked_at = now()`, sends `match_locked` push to all players, sends `deadline_warning` 1hr earlier (separate scheduled job)
4. On application restart, jobs are re-registered for any future matches (idempotent)

**Startup reconciliation:** any matches where `kickoff_utc < now()` and `status = scheduled` are locked immediately.

**Reschedule support:** when `kickoff_utc` is updated (via auto-fetch detection or admin reschedule), the existing lock job is cancelled and a new one registered. See §6.13.

### 9.2 Auto Result Fetch Job

An `IntervalTrigger` job runs every 5 minutes:

1. Fetches all WC matches from football-data.org
2. Maps to internal records via `football_data_match_id`
3. For each, takes action based on status delta (see §5.1)
4. All write operations use row-level locks (`SELECT ... FOR UPDATE`) for concurrency safety
5. Increments `consecutive_failure_count` on API error; pushes admin alert at 3
6. Updates `last_synced_at` for all checked matches
7. Idempotent — running twice with the same data produces no duplicate effects

### 9.3 Scoring Recalculation

Triggered identically whether result source is `auto`, `manual`, or `override`:

1. `matches` row updated with actual scores and `result_source` (within transaction)
2. Postgres function iterates all `predictions` for this match, calculates points (0 for no-prediction), updates `predictions.points_awarded` + `predictions.points_breakdown`
3. Same for `knockout_predictions` if applicable
4. Inserts `leaderboard_snapshots` for all players with updated totals
5. Transaction commits — Supabase Realtime broadcasts the updated leaderboard
6. Push notifications queued (respecting per-player preferences and quiet hours)

If a result is overridden, points are fully recalculated and snapshots updated. A correction entry is added to `audit_log`. Because the entire recalc happens in a single transaction, clients never see a partially-updated leaderboard.

### 9.4 Leaderboard Caching

The full leaderboard endpoint is cached per-request with a 30-second TTL in memory. Cache is invalidated on every result entry / override. For 15 players this is plenty; Realtime handles immediate updates.

### 9.5 Connection Pooling

SQLAlchemy async engine configured with:
- `pool_size = 10` — base connections held open
- `max_overflow = 10` — burst capacity
- `pool_pre_ping = True` — verify connection before use
- `pool_recycle = 1800` — recycle connections after 30 minutes (avoids stale connections in serverless environments)

### 9.6 Testing Strategy

**Backend (pytest):**
- Unit tests for scoring function — all edge cases including: exact, correct result, correct goals only, both wrong, 0-0 draw, no prediction (NULL), cancelled match
- Unit tests for lock scheduler registration + reschedule
- Unit tests for auto-fetch job: mocked API responses for FINISHED, IN_PLAY, SCHEDULED change, POSTPONED, CANCELLED, API failure, duplicate run, race with manual entry
- Unit tests for state machine transitions (valid + invalid)
- Integration tests for every API endpoint (happy path + locked match rejection + auth failure + role check)
- Minimum 80% line coverage

**Frontend (Vitest + React Testing Library):**
- Component tests for prediction card (editable / locked / postponed / cancelled states)
- Sync status widget tests (error state, success state, last-synced display)
- Leaderboard row tests (rank change animation state)
- Countdown timer tests (timezone correctness)

**End-to-end (Playwright):**
- Full player journey: join via invite → submit predictions → auto-fetch result fires → see points update
- Admin journey: verify auto-fetched result visible → override → verify recalculation
- Lock enforcement: attempt prediction after kickoff → verify rejection
- Postponement flow: API returns POSTPONED → match marked postponed → predictions preserved
- Reschedule: API returns new kickoff → new lock job registered → old job cancelled
- JWT refresh: access token expires → silent refresh → request continues seamlessly

### 9.7 CI/CD

GitHub Actions pipeline per PR:

1. Lint (ruff + ESLint + Prettier)
2. Type check (mypy + TypeScript)
3. Test (backend + frontend + E2E)
4. Build (frontend bundle + backend Docker image)
5. Migration check (Alembic applies cleanly forward + backward on a fresh DB)

On merge to `main` → auto-deploy to staging → manual promotion to production.

### 9.8 Observability

- **Sentry** captures exceptions on both ends; source maps uploaded on deploy
- **structlog** JSON logs with correlation IDs propagated through request lifecycle
- PII scrubbing — display names allowed, no other personal fields logged
- Health checks at `/health` (liveness) and `/health/ready` (DB + scheduler + football-data.org reachability)
- Slow query log enabled on Postgres at 500ms threshold

### 9.9 Operational Runbook

A `docs/runbooks/` directory contains:
- `restore.md` — restore from backup
- `kickoff-change.md` — handle a manual kickoff change
- `cancelled-match.md` — handle a cancelled match
- `pin-reset.md` — reset a player's PIN
- `auto-sync-broken.md` — what to do when football-data.org sync fails
- `tournament-end.md` — award special predictions, declare winner, archive

---

## 10. Non-Functional Requirements

### 10.1 Performance

| Metric | Target |
|---|---|
| First Contentful Paint (LCP) | < 1.5s on 4G |
| Time to Interactive | < 2.5s on 4G |
| API response (P50) | < 100ms |
| API response (P95) | < 400ms |
| Leaderboard Realtime update | < 1s from result save to client update |
| Prediction save | < 200ms (optimistic UI; actual confirmation async) |
| Service worker offline load | < 500ms |

### 10.2 Availability

- Target uptime: 99.5% during tournament window (11 Jun – 19 Jul 2026)
- Match lock jobs must fire within 60 seconds of scheduled time
- Result entry never blocked by frontend failures (admin endpoints always available)
- Auto-fetch tolerates up to 1 hour of API outage before any user impact

### 10.3 Scalability

Designed for 15 players comfortably. Scales to 50 without architectural change. Beyond that would need caching layer and read replicas — out of scope.

### 10.4 Security & Privacy

- No PII beyond display names
- No tracking or analytics by default
- All PINs bcrypt-hashed (cost 12)
- Refresh tokens SHA-256 hashed
- OWASP Top 10 considered throughout

---

## 11. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | APScheduler misses a kickoff lock | Low | High | Startup reconciliation job; manual lock override in admin panel |
| 2 | Admin forgets to enter a result | Low | Low | **Mitigated by auto-fetch** — results entered automatically; admin only needed for overrides |
| 3 | Player disputes prediction was entered before lock | Low | Medium | Audit trail with server-side timestamps; prediction locked at server, not client |
| 4 | football-data.org API unreachable during a match window | Low | Medium | Admin fallback via manual entry UI; push alert after 3 consecutive failures; manual sync trigger |
| 5 | football-data.org returns incorrect score | Very Low | Medium | Admin override available; `result_source` field makes auto vs manual clear |
| 6 | Match postponed/cancelled mid-tournament | Medium | Medium | Defined state machine (§6.13); predictions preserved on postpone, voided on cancel; push notifications |
| 7 | FIFA changes a kickoff time | Medium | Medium | Auto-detected by sync job; lock job re-registered; players notified |
| 8 | Race between auto-fetch and manual override | Low | Low | Row-level locks (`SELECT ... FOR UPDATE`); UI warns admin if data changed since form open |
| 9 | Supabase Realtime drops connection | Medium | Low | TanStack Query polling fallback every 30s if Realtime disconnects |
| 10 | Push notifications not delivered on iOS | Medium | Low | In-app notification banner as fallback; player sees updates on next app open |
| 11 | Knockout bracket matchups unclear | Medium | Medium | Admin manually sets teams for each round; placeholder text shown until set |
| 12 | Player forgets their PIN | Medium | Low | Admin can reset any player's PIN from the admin panel |
| 13 | Supabase free tier limits hit | Low | Low | Monitor monthly; free tier generous for 15 players; fallback is £20/mo Pro |
| 14 | Single admin bus factor | Medium | High | Document admin flows; runbooks per operation; auto-fetch reduces admin burden |
| 15 | Database corruption / data loss | Very Low | High | Daily Supabase snapshots; on-demand backups; documented restore procedure |
| 16 | JWT secret leak | Very Low | High | Annual rotation; revoke all refresh tokens on rotation; audit log alerts |

---

## 12. Cost Estimate

Monthly operating costs at steady-state (15 players, tournament window).

| Service | Tier | Est. Monthly Cost (GBP) |
|---|---|---|
| Supabase | Free tier (500MB DB, 1GB Storage, 2GB bandwidth) | £0 |
| football-data.org API | Free tier (personal use) | £0 |
| Backend hosting (Railway) | Hobby plan | £4 |
| Frontend hosting (Vercel) | Free tier | £0 |
| Push notifications | Free via VAPID | £0 |
| Sentry | Free tier | £0 |
| Domain name | Annual ~£12 | £1 |
| **Total** | | **~£5/month** |

*The tournament runs 39 days. Total cost for the tournament window: ~£7. The auto-fetch feature costs nothing additional.*

---

## 13. Conventions

### 13.1 Naming

| Context | Convention | Example |
|---|---|---|
| Database tables | snake_case plural | `knockout_predictions` |
| Database columns | snake_case | `predicted_home` |
| Python (backend) | snake_case | `def calculate_points()` |
| TypeScript vars/funcs | camelCase | `calculatePoints()` |
| TypeScript components | PascalCase | `PredictionCard.tsx` |
| JSON API fields | camelCase | `"predictedHome": 2` |
| Environment variables | SCREAMING_SNAKE | `FOOTBALL_DATA_API_KEY` |
| Git branches | kebab-case with prefix | `feat/knockout-bracket` |

### 13.2 API Response Shapes

**Success (single):**
```json
{ "data": { "id": "...", "predictedHome": 2 }, "meta": null, "errors": null }
```

**Success (list):**
```json
{ "data": [...], "meta": { "page": 1, "per_page": 20, "total": 104 }, "errors": null }
```

**Error:**
```json
{ "data": null, "meta": null, "errors": [{ "code": "PREDICTION_LOCKED", "message": "...", "field": null }] }
```

### 13.3 Git Workflow

- **Main branch:** `main` — always deployable
- **Feature branches:** `feat/<description>` branched from main
- **Bug fixes:** `fix/<description>`
- **Chores:** `chore/<description>`
- **Commits:** Conventional Commits — `feat:`, `fix:`, `chore:`, `docs:`, `test:`
- **PRs:** require passing CI + reviewer (or self-review checklist for solo dev)
- **Squash merge** into main

### 13.4 Code Organisation

```
/
├── apps/
│   ├── api/              # FastAPI backend
│   └── web/              # React frontend (Vite)
├── packages/
│   └── shared/           # Shared Zod schemas, TS types, scoring logic
├── migrations/           # Alembic migrations
├── docs/
│   ├── adr/              # Architecture decision records
│   └── runbooks/         # Operational runbooks
└── .github/workflows/    # CI/CD
```

---

## 14. Entity Relationships & Glossary

### 14.1 Entity Relationship Overview

```
profiles ──┬── 1:N ──── refresh_tokens
           ├── 1:N ──── invites (created_by, claimed_by)
           ├── 1:N ──── push_subscriptions
           ├── 1:1 ──── notification_preferences
           ├── 1:N ──── notification_log
           ├── 1:N ──── predictions ──── N:1 ──── matches ──── N:1 ──── groups
           ├── 1:N ──── knockout_predictions ──── N:1 ──── matches
           ├── 1:N ──── special_predictions ──── N:1 ──── teams
           └── 1:N ──── leaderboard_snapshots ──── N:1 ──── matches (triggered_by)

matches ──── N:1 ──── teams (home, away, penalty_winner)
matches ──── N:1 ──── groups
teams ──── N:1 ──── groups

audit_log ──── N:1 ──── profiles (actor, nullable for system actions)
audit_log ──── target_table + target_id  (polymorphic reference)
```

### 14.2 Glossary

| Term | Definition |
|---|---|
| **Admin** | The league organiser — manages invites, oversees results, handles overrides |
| **Player** | A league participant who submits predictions and competes on the leaderboard |
| **Match** | A single football game — group stage or knockout |
| **Prediction** | A player's predicted scoreline for a match |
| **Knockout prediction** | A player's prediction of who wins a knockout match (separate from score prediction) |
| **Special prediction** | Pre-tournament bonus: tournament winner, Golden Boot, top scoring team |
| **Lock** | The moment a match's predictions become immutable (at kickoff) |
| **Result** | The actual score, set automatically by auto-fetch or manually by admin |
| **Result source** | How a result was recorded: `auto`, `manual`, or `override` |
| **Points breakdown** | Per-match detail of how points were earned (goals / result / exact) |
| **Leaderboard snapshot** | Point-in-time record of all players' standings after each result |
| **Invite** | A single-use URL that allows a new player to join the league |
| **Audit trail** | Timestamped record of all prediction submissions and admin actions |
| **Round** | A stage of the tournament (group, R32, R16, QF, SF, third place, Final) |
| **Head-to-head** | Side-by-side comparison of two players' predictions across all completed matches |
| **Auto-fetch** | The 5-minute scheduled job that pulls results from football-data.org |
| **Reschedule** | A change to a match's `kickoff_utc` that triggers re-registration of its lock job |

---

## 15. Deployment Strategy

### 15.1 Local Development

- Frontend: Vite dev server on port 5173
- Backend: Uvicorn (FastAPI) on port 8000
- Database: Supabase cloud (free tier) — no local DB setup needed
- Scheduler: runs in-process with Uvicorn

### 15.2 Production

| Option | Frontend | Backend | Cost |
|---|---|---|---|
| Vercel + Railway | Vercel (free) | Railway container | ~£4/mo |
| Fly.io | Static files | Docker container | Free tier available |
| Self-hosted | Nginx | Systemd service | Hardware only |

---

## 16. Build Phases

### Session Protocol

**At the start of every session, print:**

```
=== PHASE [ID]: [NAME] ===
Model: [Sonnet 4.6 / Opus]
Status: [ ] Not started / [~] In progress / [✅] Complete

ACCEPTANCE CRITERIA:
- [ ] [criterion 1]
- [ ] [criterion 2]

Starting now.
```

**At the end of every session — phase close-out:**

Follow the global phase close-out protocol defined in `~/.claude/CLAUDE.md` exactly. Project-specific variables are declared in the repo's `CLAUDE.md`:

- Session log: `session-log.md` (repo root)
- Architecture/plan doc: `wc2026-architecture.md` (repo root)
- Remote: `origin main`
- CI: GitHub Actions — poll via GitHub API with token from env `GITHUB_TOKEN`

The close-out protocol handles: acceptance criteria sign-off, session log update, architecture doc sync, git commit + push, CI poll, and next phase declaration. A phase is **not complete** until the protocol finishes cleanly.

### Model Guide

| Tag | When to use |
|---|---|
| 🟢 **Sonnet 4.6** | Straightforward implementation — CRUD, components, migrations, tests, API wiring. The default. |
| 🔴 **Opus** | Complex reasoning — scoring edge cases, bracket logic, scheduler design, realtime sync, debugging. |

---

### Stage 0 — Foundations

**Phase 0.1: Repository Scaffolding** 🟢 Sonnet 4.6 ✅ 2026-05-06
- Monorepo structure (`apps/api`, `apps/web`, `packages/shared`, `migrations`, `docs`)
- Git initialised, `.gitignore`, README, `.env.example`
- Node + Python versions pinned, `pnpm` workspace configured
- **Acceptance:** `pnpm install` works; repo structure matches spec

**Phase 0.2: Backend Skeleton** 🟢 Sonnet 4.6 ✅ 2026-05-06
- FastAPI app with `/api/v1/health` and `/api/v1/health/ready`
- Pydantic settings loader with `.env.example`
- Uvicorn dev server, Dockerfile
- SQLAlchemy async engine with connection pool config
- Ruff + mypy configured, structlog integrated
- **Acceptance:** `uvicorn` starts, `/health` returns 200, lint passes

**Phase 0.3: Frontend Skeleton** 🟢 Sonnet 4.6 ✅ 2026-05-06
- Vite + React 18 + TypeScript strict mode
- Tailwind configured with full design token CSS variables (§7.2 colours, typography)
- shadcn/ui initialised with Button, Card, Badge components
- Dark mode default (deep navy theme)
- Bebas Neue + Outfit fonts loaded
- **Acceptance:** `pnpm dev` starts; design tokens applied; correct colour palette visible

**Phase 0.4: Supabase Setup & Auth** 🟢 Sonnet 4.6 ✅ 2026-05-09
- Supabase project created, credentials in `.env.example`
- `profiles` + `refresh_tokens` tables + RLS policies
- Name + PIN login flow with refresh token rotation
- JWT pair stored in localStorage, silent refresh implemented
- Protected routes (admin vs player)
- **Acceptance:** Can log in as admin; refresh flow works silently; player routes redirect unauthenticated users; admin endpoints reject player tokens

**Phase 0.5: CI Pipeline** 🟢 Sonnet 4.6 ✅ 2026-05-06
- GitHub Actions: lint, typecheck, unit test, build, migration check (forward + backward)
- Runs on every PR
- **Acceptance:** PR shows green checks; failing lint or migration blocks merge

**Phase 0.6: Error Tracking** 🟢 Sonnet 4.6 ✅ 2026-05-06
- Sentry integrated (frontend + backend)
- structlog with correlation IDs on all requests
- PII scrubbing configured
- **Acceptance:** Test error appears in Sentry; logs include correlation IDs; no display names leak to logs

---

### Stage 1 — Data & Tournament Seed

**Phase 1.1: Core Schema — Profiles, Refresh Tokens, Invites, Teams, Groups** 🟢 Sonnet 4.6 ✅ 2026-05-06
- Alembic initialised
- Migration for `profiles` (with `failed_login_count`, `locked_until`, `timezone`), `refresh_tokens`, `invites`, `teams` (with `eliminated_at_stage` ENUM and `football_data_team_id`), `groups`
- `updated_at` trigger helper applied
- **Acceptance:** Migrations apply and rollback cleanly

**Phase 1.2: Match Schema** 🟢 Sonnet 4.6 ✅ 2026-05-08
- Migration for `matches` with full state machine ENUM (scheduled, locked, live, completed, postponed, cancelled), `result_source` ENUM, `original_kickoff_utc`, `postponed_reason`
- UNIQUE constraint on `match_number` and `football_data_match_id`
- Indexes on `kickoff_utc`, `(stage, status)`, `football_data_match_id`
- **Acceptance:** Table exists; ENUM values enforced; indexes verified via `EXPLAIN`

**Phase 1.3: Prediction & Notification Schema** 🟢 Sonnet 4.6 ✅ 2026-05-08
- Migration for `predictions` (with `update_count` default 0), `knockout_predictions`, `special_predictions`
- Unique constraints on `(player_id, match_id)` and `(player_id, prediction_type)`
- Migration for `leaderboard_snapshots`, `push_subscriptions`, `notification_preferences`, `notification_log`, `audit_log` (with full ENUM lists)
- **Acceptance:** Full schema deployed; FKs enforced; default values verified; test data insertable

**Phase 1.4: Tournament Data Seed** 🟢 Sonnet 4.6 ✅ 2026-05-08
- Seed script inserts all 12 groups (A–L)
- Seed script inserts all 48 teams with flags, group assignment, `football_data_team_id`
- Seed script inserts all 72 group stage matches with kickoff times, venues, teams, `football_data_match_id`
- Idempotent (safe to re-run)
- **Acceptance:** After seed, all 72 group matches queryable with correct teams, kickoff times, and football-data IDs

**Phase 1.5: Scoring Function** 🔴 Opus ✅ 2026-05-08
- Postgres function `calculate_match_points(predicted_home, predicted_away, actual_home, actual_away, stage)` returns JSONB breakdown
- Handles group stage rules (W/D/L for result; combined goals)
- Handles knockout score predictions (no draws — result is always W/L based on 90-min score)
- Returns 0 for NULL predictions with `no_prediction: true` flag
- Edge cases: 0-0 draw, same total goals different result, knockout draw at 90, NULL prediction
- Unit tests covering 25+ edge cases
- **Acceptance:** All test cases return correct points; function called within a transaction

**Phase 1.6: Scoring Trigger & Snapshot Insert** 🔴 Opus ✅ 2026-05-08
- Postgres trigger on `matches` UPDATE: when scores set, calls scoring function for all predictions
- Updates `predictions.points_awarded` + `predictions.points_breakdown`
- Same for `knockout_predictions` (if knockout match)
- Inserts `leaderboard_snapshots` for all active players with updated totals
- All within a single transaction (atomic — clients never see partial updates)
- **Acceptance:** Entering a result via SQL updates all predictions and leaderboard atomically; concurrent reads never see partial state

---

### Stage 2 — Auth & Player Management

**Phase 2.1: Invite API** 🟢 Sonnet 4.6 ✅ 2026-05-09
- `POST /api/v1/admin/invites` — create invite (optional name hint, expiry)
- `GET /api/v1/admin/invites` — list all
- `DELETE /api/v1/admin/invites/{id}` — revoke
- Integration tests
- **Acceptance:** Admin creates invite; token is unique; deletion revokes access

**Phase 2.2: Join Flow API** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `POST /api/v1/auth/join` — validate token, check display_name uniqueness, create profile + notification_preferences row, issue JWT pair
- Enforce max 15 active players at claim time
- Mark invite as claimed
- **Acceptance:** Valid token creates player + default preferences; second use rejected; 16th player rejected; duplicate name rejected

**Phase 2.3: Login & Refresh API** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `POST /api/v1/auth/login` — name + PIN, return JWT pair, manage `failed_login_count` and `locked_until`
- `POST /api/v1/auth/refresh` — exchange refresh token for new pair (with rotation)
- `POST /api/v1/auth/logout` — invalidate refresh token
- `GET /api/v1/auth/me`
- `PUT /api/v1/auth/me/pin` — change own PIN (requires current PIN verification)
- `POST /api/v1/admin/players/{id}/reset-pin`
- **Acceptance:** Correct PIN returns JWT pair; wrong PIN increments counter; 5th fail locks for 15 min; refresh rotates token; logout invalidates

**Phase 2.4: Player API** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `GET /api/v1/players` — list active players (`is_active = true`)
- `GET /api/v1/players/{id}` — profile + stats stub (works for soft-deleted too, with flag)
- `DELETE /api/v1/admin/players/{id}` — soft delete (`is_active = false`)
- **Acceptance:** Admin removes player; player can no longer log in; predictions and stats preserved historically; player hidden from default leaderboard

**Phase 2.5: Join & Login UI** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `/join/{token}` page — name confirm + PIN creation form
- `/login` page — name dropdown + PIN entry
- Error states (locked account, invalid PIN, duplicate name)
- JWT pair stored, silent refresh wired up
- **Acceptance:** Full join flow works end-to-end; locked account shows lockout time; expired access token silently refreshes

**Phase 2.6: Admin Invite & Player UI** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `/admin/invites` — generate, list, revoke
- `/admin/players` — list, remove, reset PIN
- Reset PIN flow returns a temporary PIN to admin (displayed once, copy to clipboard)
- **Acceptance:** Admin manages invites and players; reset PIN works; player can log in with temp PIN and change it

---

### Stage 3 — Matches & Schedule

**Phase 3.1: Match API** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `GET /api/v1/matches`, `/{id}`, `/upcoming`, `/live`, `/stage/{stage}`
- All status states surfaced (scheduled, locked, live, completed, postponed, cancelled)
- **Acceptance:** All 72 seeded matches returned correctly; filters work; kickoff times in UTC

**Phase 3.2: Groups API** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `GET /api/v1/groups` and `/groups/{name}` with FIFA tiebreaker rules
- `POST /api/v1/admin/groups/{name}/override-standings` for manual tiebreakers
- **Acceptance:** After seeding 3 test results in Group A, standings reflect correct order; override sets exact positions

**Phase 3.3: Match Schedule UI** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `/schedule` page — matches grouped by date
- Match card component: teams, flags, kickoff time (player's IANA timezone via `date-fns-tz`), venue, full status pill set
- Countdown timer for upcoming matches
- Filter bar: by group, by stage, by date range, by team
- **Acceptance:** All 72 matches visible; filters work; countdown accurate to player's timezone; postponed/cancelled matches visually distinct

**Phase 3.4: Group Standings UI** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `/groups` and `/groups/{name}` pages
- Supabase Realtime subscription — table updates when result entered
- **Acceptance:** Entering a test result in admin immediately updates the group table in another browser tab

**Phase 3.5: Match Lock Scheduler & Reschedule Handling** 🔴 Opus ✅ 2026-05-10
- APScheduler integration in FastAPI startup
- On startup: register `DateTrigger` lock job for every scheduled match
- Lock job: sets `status = locked`, `locked_at = now()`, fires push
- Startup reconciliation for past-due scheduled matches
- Reschedule API (`PUT /admin/matches/{id}/reschedule`): updates `kickoff_utc`, sets `original_kickoff_utc`, cancels old lock job, registers new one, pushes `kickoff_changed`
- Postpone (`POST /admin/matches/{id}/postpone`) and cancel (`POST /admin/matches/{id}/cancel`) endpoints with state machine validation
- Unit tests for all transitions and reschedule scenarios
- **Acceptance:** Setting a match kickoff 5 seconds in future triggers lock at the right time; rescheduling re-registers the job; postponing preserves predictions; cancelling voids them

---

### Stage 4 — Predictions

**Phase 4.1: Prediction API** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `PUT /api/v1/predictions/{match_id}` — submit/update (rejected if status ≠ scheduled)
- `GET /api/v1/predictions/me`
- `GET /api/v1/predictions/match/{match_id}` (post-lock only — checks status)
- `GET /api/v1/predictions/player/{player_id}` (post-lock only)
- Audit: `submitted_at` set on first save, `updated_at` auto, `update_count` increments
- **Acceptance:** Prediction saved before lock; rejected after lock with `PREDICTION_LOCKED`; another player's predictions hidden pre-lock

**Phase 4.2: My Predictions UI** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `/predictions` page with group tabs (A–L)
- Prediction card per match
- Locked / postponed / cancelled matches: read-only with appropriate visual state
- Points badge appears once result entered
- Save button per group with debounced autosave
- **Acceptance:** Player submits all Group A predictions; locked matches show as read-only; cancelled matches show voided

**Phase 4.3: Prediction Card Polish** 🟢 Sonnet 4.6 ✅ 2026-05-11
- Score input: number spinner, large Bebas Neue font
- Lock indicator: padlock icon + "Kicks off in Xh Ym" countdown
- Points badge animation on result reveal (count-up)
- "Not predicted" warning state
- Deadline warning style (orange) when < 1hr to kickoff
- **Acceptance:** Visual states correct across all match statuses; animation plays on points reveal

**Phase 4.4: Match Detail Page** 🟢 Sonnet 4.6 ✅ 2026-05-10
- `/matches/{id}` — all players' predictions in a comparison table (post-lock)
- Pre-lock: shows only own prediction + lock countdown
- Cancelled match: shows voided notice, no scoring
- **Acceptance:** Visibility rules enforced; cancelled state clear

---

### Stage 5 — Results & Auto-Fetch

**Phase 5.1: Admin Results API** 🟢 Sonnet 4.6 ✅ 2026-05-11
- `POST /admin/results/{match_id}` — manual entry (fallback)
- `PUT /admin/results/{match_id}` — override
- Validates match is `locked`, `live`, or `completed` (not `scheduled`/`postponed`/`cancelled`)
- Sets `result_source` correctly (`manual` if no prior result, `override` if overwriting auto)
- Triggers scoring; logs to audit
- **Acceptance:** Manual entry works; override recalculates; source field correct in each case

**Phase 5.2: football-data.org Client** 🟢 Sonnet 4.6 ✅ 2026-05-11
- Python API client for v4
- Typed Pydantic models for match response
- Rate-limit-aware
- `FOOTBALL_DATA_API_KEY` in env
- Unit tests: FINISHED, IN_PLAY, SCHEDULED kickoff change, POSTPONED, CANCELLED, 429, 5xx
- **Acceptance:** Client fetches all WC matches; all status types map correctly; handles errors gracefully

**Phase 5.3: Auto Result Fetch Job** 🔴 Opus ✅ 2026-05-11
- APScheduler `IntervalTrigger` every 5 minutes
- Full status delta handling (§5.1)
- Row-level locks (`SELECT ... FOR UPDATE`) for concurrency safety
- Idempotent — second run with same data = no-op
- Failure counter; admin alert at 3 consecutive failures
- Logs to `audit_log` with `actor_type = system`
- Triggers scoring pipeline identical to manual entry path
- Unit tests: new result, existing match update, race with manual, postponed detection, kickoff change detection, API failure
- **Acceptance:** Full status flow tested with mocked API; race condition handled correctly; reschedule triggers lock-job re-registration

**Phase 5.4: Admin Sync UI** 🟢 Sonnet 4.6 ✅ 2026-05-12
- `/admin/sync` — sync status, last run time, next run countdown, error log
- "Sync Now" button
- Sync status widget on admin dashboard
- `/admin/results` updated to show source badges
- **Acceptance:** Admin sees last sync; manual trigger works; error state visible

**Phase 5.5: Points Reveal** 🟢 Sonnet 4.6 ✅ 2026-05-12
- Result detected → Realtime broadcast → prediction card animates
- Toast notification with points scored
- **Acceptance:** Two browser tabs; auto-fetch fires; player tab animates within 2 seconds without admin action

**Phase 5.6: Admin Dashboard** 🟢 Sonnet 4.6 ✅ 2026-05-12
- `/admin` — sync status widget, upcoming locks (next 24hrs), pending overrides, active players, recent audit entries
- **Acceptance:** All widgets populated; error state visible when API failing

---

### Stage 6 — Leaderboard

**Phase 6.1: Leaderboard API** 🟢 Sonnet 4.6 ✅ 2026-05-12
- `GET /leaderboard`, `/history`, `/round/{stage}`
- Excludes inactive players by default; admin flag `?include_inactive=true`
- **Acceptance:** Totals correct after multiple results; round filter works; inactive players hidden by default

**Phase 6.2: Leaderboard UI** 🟢 Sonnet 4.6 ✅ 2026-05-12
- `/leaderboard` page with rank, medal, name, total, breakdown
- Realtime subscription
- **Acceptance:** Live updates; rank arrows correct; expand/collapse works

**Phase 6.3: Leaderboard History Chart** 🟢 Sonnet 4.6 ✅ 2026-05-12
- `/leaderboard/history` — Recharts line chart of rank per player over time
- Aggregated by `snapshot_at` timestamp (one x-axis point per result)
- Player toggle for lines
- **Acceptance:** After 10 test results entered, chart shows 10 x-axis points (per-result snapshots), 15 lines (one per active player)

**Phase 6.4: Round Leaderboard** 🟢 Sonnet 4.6 ✅ 2026-05-12
- `/leaderboard/round/{stage}` — round-specific points only
- **Acceptance:** Selecting a round shows only that round's points; ordering may differ from overall

---

### Stage 7 — Knockout Bracket

**Phase 7.1: Knockout Match Creation API** 🔴 Opus ✅ 2026-05-14
- `POST /admin/knockout/advance` — creates next round's matches with correct seeding
- Pulls kickoff times from football-data.org client during creation
- Validates advancing teams have correct results
- **Acceptance:** After group stage, admin advances to R32; all 16 R32 matches created with teams + kickoffs

**Phase 7.2: Knockout Prediction API** 🟢 Sonnet 4.6 ✅ 2026-05-15
- `PUT /knockout-predictions/{match_id}`
- `GET /knockout-predictions/me`
- `GET /knockout-predictions/match/{match_id}` (post-round-lock)
- **Acceptance:** Predictions submitted for R32; locked at first R32 kickoff; points awarded on result

**Phase 7.3: Bracket Visualisation** 🔴 Opus ✅ 2026-05-15
- `/bracket` — interactive SVG bracket tree
- Placeholder text for unset matchups
- Predicted winners shown in player's avatar colour
- Correct predictions highlighted post-result
- Mobile-responsive (horizontal scroll)
- **Acceptance:** Bracket renders all rounds; predicted winners visible; responsive on mobile

**Phase 7.4: Knockout Prediction UI** 🟢 Sonnet 4.6 ✅ 2026-05-15
- `/predictions/knockout` with round tabs
- Lock countdown per round
- **Acceptance:** Player picks winners for all R32 matches; locked at first kickoff *(superseded by U22.1 — now per-match)*

---

### Stage 8 — Special Predictions

**Phase 8.1: Special Predictions API** 🟢 Sonnet 4.6 ✅ 2026-05-15
- `GET /specials`, `PUT /specials/{type}`, `GET /specials/all`
- `POST /admin/specials/award`
- Locked at tournament opening kickoff
- **Acceptance:** All 3 specials submitted; locked correctly; admin awards at tournament end

**Phase 8.2: Special Predictions UI** 🟢 Sonnet 4.6 ✅ 2026-05-15
- `/predictions/specials` — team pickers + free text
- Lock countdown to opening kickoff
- Post-lock comparison view
- **Acceptance:** Submission flow works; comparison visible after lock

---

### Stage 9 — Stats & Comparison

**Phase 9.1: Stats API** 🟢 Sonnet 4.6 ✅ 2026-05-15
- `GET /stats/me`, `/stats/{player_id}`, `/stats/league`
- Calculate: accuracy %, exact rate, avg pts, best/worst round, current streak, prediction timing
- **Acceptance:** Stats correct from test data; endpoints under 200ms

**Phase 9.2: Player Profile UI** 🟢 Sonnet 4.6 ✅ 2026-05-15
- `/players/{id}` — profile, stat cards, recent predictions, head-to-head mini table
- **Acceptance:** Stats display correctly; accessible from leaderboard row

**Phase 9.3: Head-to-Head API** 🟢 Sonnet 4.6 ✅ 2026-05-15
- `GET /compare/{player_a_id}/{player_b_id}`
- Handles edge cases (one player didn't predict; one player removed)
- **Acceptance:** Comparison data correct including edge cases

**Phase 9.4: Head-to-Head UI** 🔴 Opus ✅ 2026-05-15
- `/compare` — player picker + side-by-side comparison
- Summary bar with W/D/L
- Long-press from leaderboard
- **Acceptance:** Comparison renders; winner per match highlighted; summary correct

---

### Stage 10 — Notifications & PWA

**Phase 10.1: PWA Setup** 🟢 Sonnet 4.6 ✅ 2026-05-16
- Web App Manifest
- Service worker registration
- Install prompt
- Offline fallback page
- **Acceptance:** Installable on iOS and Android; offline page shows when no connection

**Phase 10.2: Web Push Backend** 🟢 Sonnet 4.6 ✅ 2026-05-16
- VAPID key generation
- Subscription endpoints
- pywebpush integration
- `send_notification(player_id, type, title, body, data)` helper that respects preferences + quiet hours + global mute
- Failed-send tracking; auto-disable after 3 fails
- **Acceptance:** Test push delivered; suppressed notifications logged correctly; failed subscriptions auto-disabled

**Phase 10.3: Notification Triggers** 🟢 Sonnet 4.6 ✅ 2026-05-16
- Wire all 10 trigger types: deadline_warning, match_locked, result_detected, leaderboard_shift, round_complete, match_postponed, kickoff_changed, invite_accepted, auto_sync_failed, special_results
- All logged to `notification_log` with appropriate status
- **Acceptance:** Each trigger type tested; all delivered correctly with preferences respected

**Phase 10.4: Notification Preferences UI** 🟢 Sonnet 4.6 ✅ 2026-05-16
- `/settings` — per-category toggles, global mute, quiet hours
- Test notification button
- PWA install prompt
- **Acceptance:** Preferences persist; quiet hours suppress correctly; test push works

---

### Stage 11 — Polish & Resilience

**Phase 11.1: Home Dashboard** 🟢 Sonnet 4.6 ✅ 2026-05-16
- `/` — rank, points, next match countdown, latest result, mini leaderboard
- **Acceptance:** Loads in < 1.5s; all widgets correct

**Phase 11.2: Offline Support** 🔴 Opus ✅ 2026-05-16
- Service worker caches schedule, predictions, leaderboard
- Stale-while-revalidate for match data
- Write queue for offline prediction saves
- Offline banner
- **Acceptance:** Schedule + predictions browsable offline; submitted prediction syncs on reconnect

**Phase 11.3: Optimistic UI** 🟢 Sonnet 4.6 ✅ 2026-05-16
- Prediction save optimistic; rollback with toast on failure
- **Acceptance:** Instant save UX; network failure rolls back cleanly

**Phase 11.4: Backup & Restore** 🟢 Sonnet 4.6 ✅ 2026-05-16
- `POST /admin/backup`, `GET /admin/backups`, download endpoint
- `docs/runbooks/restore.md` written and tested
- Pre-tournament automated backup configured
- **Acceptance:** Manual backup works; runbook tested by performing a real restore on a staging copy

**Phase 11.5: Operational Runbooks** 🟢 Sonnet 4.6 ✅ 2026-05-16
- All runbooks in `docs/runbooks/` (restore, kickoff-change, cancelled-match, pin-reset, auto-sync-broken, tournament-end)
- **Acceptance:** Each runbook has clear step-by-step instructions; admin can follow without dev knowledge

**Phase 11.6: Accessibility Pass** 🟢 Sonnet 4.6 ✅ 2026-05-16
- Keyboard reachable, ARIA labels, contrast ≥ 4.5:1
- VoiceOver + NVDA tested
- `prefers-reduced-motion` respected
- **Acceptance:** axe-core 0 violations; keyboard navigation works throughout

**Phase 11.7: Playwright E2E Tests** 🟢 Sonnet 4.6 ✅ 2026-05-16
- Critical flows: join → predict → auto-fetch result → see points → leaderboard update
- Lock enforcement
- Reschedule flow
- Postponement flow
- JWT refresh
- Head-to-head
- Admin override
- Runs on Chromium + Firefox + WebKit in CI
- **Acceptance:** All flows pass on CI

**Phase 11.8: Visual Polish & Empty States** 🔴 Opus ✅ 2026-05-17
- Empty states for every list
- Loading skeletons
- Error boundaries
- Page transitions (Framer Motion)
- Lighthouse scores ≥ 90
- **Acceptance:** No blank states; Lighthouse verified

**Phase 12.1: Knockout Scoring Cleanup** 🟢 Sonnet 4.6 ✅ 2026-06-02
- Grade the 90-minute knockout score identically to a group score: a 90-min draw is a valid result, since the advance (knockout-winner) pick now owns "who goes through"
- New migration: `CREATE OR REPLACE FUNCTION calculate_match_points` dropping the `is_knockout` draw-void branch; downgrade restores it
- Mirror the change in `packages/shared/src/scoring.ts` (remove the `isKnockout` clauses) — the SQL and TS scorers must stay in parity
- Update §6.1 wording (remove the "scored as a draw / no result points" description)
- Update scoring tests (`test_scoring_function.py`, `test_scoring_trigger.py`, `scoring.test.ts`): exact 1-1 knockout 7→10; correctly calling a knockout draw direction earns the +3 result
- **Acceptance:** SQL and TS produce identical breakdowns for every stage; exact knockout draw scores 10; no knockout-specific result suppression remains; all scoring tests green

**Phase 12.2: Specials Expansion — Player of the Tournament, Young Player, Golden Glove** 🟢 Sonnet 4.6 ✅ 2026-06-02
- Add three player specials: Player of the Tournament (15), Young Player of the Tournament (10), Golden Glove (10)
- Migration: `ALTER TYPE special_prediction_type ADD VALUE` ×3 (values-only migration; respect the enum-add-value transaction rule)
- `SpecialPredictionType` enum gains 3 members; no `special_predictions` table change (`predicted_player_id` / `winner_player_id` already exist from migration 020)
- `routers/specials.py`: extend `SPECIAL_POINTS`; introduce a `PLAYER_SPECIALS` set and generalize the `== golden_boot` branches (upsert + award) to set membership
- `routers/squad.py`: add an optional `position` filter to `/squad/search` so Golden Glove restricts to GK; Young Player stays unfiltered (roster carries no date of birth) with the admin adjudicating the actual winner
- Frontend `SpecialsPage.tsx`: three player-typeahead inputs reusing the U14 Golden Boot combobox; admin specials-award UI gains the three new player-winner controls
- Update §3.9, §6.1, §6.5 (specials total → 80; grand total → ≈1,415)
- Tests: `test_specials.py` (3 new types via the generalized player path) and `SpecialsPage.test.tsx`
- **Acceptance:** players can submit/update all three before the opening-match lock; the Golden Glove picker is GK-only; admin award writes 15/10/10 into `special_points` and the leaderboard; all players' picks visible post-lock; tests green

---

### Phase Count & Summary

| Stage | Phases | Focus |
|---|---|---|
| 0 — Foundations | 6 | Repo, backend, frontend, auth (with refresh), CI, error tracking |
| 1 — Data & Seed | 6 | Schema (full state machine, refresh tokens, notif prefs), tournament data, scoring |
| 2 — Auth & Players | 6 | Invite flow, login + refresh, player management with PIN reset |
| 3 — Matches & Schedule | 5 | Match API, schedule UI, group standings, lock scheduler with reschedule |
| 4 — Predictions | 4 | Prediction API, UI, match detail (handling all match statuses) |
| 5 — Results & Auto-Fetch | 6 | Admin results, API client, auto-fetch with full status handling, sync UI, points reveal, dashboard |
| 6 — Leaderboard | 4 | Leaderboard API, live UI, history chart, round filter |
| 7 — Knockout Bracket | 4 | Knockout creation, predictions, bracket visual |
| 8 — Special Predictions | 2 | API + UI for tournament specials |
| 9 — Stats & Comparison | 4 | Stats API, player profiles, head-to-head |
| 10 — Notifications & PWA | 4 | PWA, Web Push (with preferences/quiet hours), all 10 triggers, preferences UI |
| 11 — Polish & Resilience | 8 | Dashboard, offline, optimistic UI, backup, runbooks, accessibility, E2E, polish |
| 12 — Scoring & Specials Refresh | 2 | Knockout draw-void cleanup; three new player specials (POTT, Young Player, Golden Glove) |
| **Total** | **61** | |

**Recommended pace:** 1–2 phases per session. Tournament starts 11 June 2026 — build should complete by early June with 2 weeks buffer for real-world testing.

---

## 17. Resolved Decisions

| # | Decision | Resolution |
|---|---|---|
| 1 | Tournament format | 2026 real format — 48 teams, 12 groups, R32 → Final, plus 3rd Place Play-off |
| 2 | Scoring system | 2pts correct goals, 3pts correct result, 5pts exact score. Max 10pts/match |
| 3 | Prediction locking | Per-match at kickoff |
| 4 | Authentication | Name + PIN with bcrypt; JWT access + refresh token pair (24h / 30d) |
| 5 | League access | Invite only — admin sends single-use links |
| 6 | Max players | 15 |
| 7 | Notifications | Push notifications via PWA; per-category preferences with quiet hours and global mute |
| 8 | Backend stack | FastAPI + Supabase + PostgreSQL |
| 9 | Frontend stack | React 18 + Tailwind + shadcn/ui |
| 10 | Knockout predictions | Round-by-round winner picks: R32=5, R16=10, QF=15, SF=20, 3rd Place=10, Final=25 (max 295pts total) |
| 11 | Special predictions | 3 pre-tournament: winner (20pts), Golden Boot (15pts), top scoring team (10pts) |
| 12 | Score display | Bebas Neue for numbers — athletic, tournament-feel |
| 13 | Prediction visibility | Hidden from other players until match locks |
| 14 | Result override | Available to admin with mandatory audit log entry |
| 15 | Player PIN reset | Admin can reset any player's PIN; temporary PIN displayed once |
| 16 | Knockout bracket predictions | Round-by-round, not whole-tournament upfront |
| 17 | Tiebreakers | FIFA rules; admin override available for edge cases |
| 18 | Leaderboard real-time | Supabase Realtime; 30s polling fallback |
| 19 | Prediction audit | Server-side timestamps; backdating impossible; cancelled matches void predictions |
| 20 | Extra time / penalties | 90-minute score used for prediction scoring; penalty winner tracked separately |
| 21 | Offline support | Service worker caches schedule + predictions; write queue syncs on reconnect |
| 22 | Deployment | Vercel (frontend) + Railway (backend) — ~£5/month |
| 23 | Testing strategy | pytest + Vitest + Playwright; ≥80% coverage; tests ship with each phase |
| 24 | Head-to-head | Available for any two players (including soft-deleted) |
| 25 | Player stats | Accuracy %, exact rate, avg points, streaks, prediction timing |
| 26 | Auto result fetching | football-data.org API, 5-min polling, full status handling |
| 27 | Result source tracking | `result_source` ENUM (auto / manual / override) |
| 28 | Auto-fetch failure handling | Push admin alert after 3 consecutive failures; manual entry fallback |
| 29 | Auto vs manual precedence | Auto never overwrites manual or override; updates auto-only results if API corrects |
| 30 | Live match status | `IN_PLAY` from API → `matches.status = live` |
| 31 | Postponement handling | Predictions preserved; match removed from scoring until rescheduled |
| 32 | Cancellation handling | Predictions voided; no points; clear UI marker |
| 33 | Reschedule handling | Auto-detected; lock job re-registered; players notified |
| 34 | Race condition handling | Row-level locks (`SELECT ... FOR UPDATE`); admin form warns on stale data |
| 35 | No prediction = 0 points | Explicit; flagged in breakdown JSON |
| 36 | Soft-deleted players | Hidden from default leaderboard; preserved historically; visible in head-to-head |
| 37 | Notification preferences | Dedicated table; per-category, quiet hours, global mute |
| 38 | Backup strategy | Daily Supabase snapshot + on-demand `pg_dump` to Storage; pre-tournament snapshot; documented restore |
| 39 | JWT token strategy | 24h access + 30d refresh; silent refresh from frontend; refresh tokens hashed in DB |
| 40 | Connection pooling | SQLAlchemy async pool, size 10, overflow 10, recycle 30min |
| 41 | Operational runbooks | All admin procedures documented in `docs/runbooks/` |

---

*Version 1.2 — Final. This document is the authoritative design specification for implementation. Update this document in the same PR as any architectural change.*

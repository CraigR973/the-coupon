# Runbook — launch readiness check

What to verify before a first live Saturday, and what production actually
contained when this was last run. Every query here is **read-only**.

Run it from this repository with the Railway CLI authenticated as the owner.
The production database host is IPv6-only, so a local process cannot reach it —
use `railway ssh` and run `psql` *inside* the service.

## 1. Data readiness

```bash
railway ssh --project e030ebe3-e7fc-43c9-9478-4e80cafaa126 \
  --environment 8f18cb49-5137-4557-900a-031bcab4ac38 \
  --service d59f4f17-3e7d-4b3b-bf40-30620150fa2f \
  'U="${DATABASE_URL/postgresql+asyncpg/postgresql}"; U="${U%%\?*}"; psql "$U" -c "
select l.slug, g.starts_on, g.status, g.number, g.picks_open_at_utc, g.locks_at_utc,
 (select count(*) from gameweek_fixtures gf where gf.gameweek_id=g.id) as fixtures,
 (select count(*) from picks p where p.gameweek_id=g.id) as picks
from gameweeks g join leagues l on l.id=g.league_id order by g.starts_on desc limit 6;"'
```

Also worth counting: `profiles` (excluding `deleted_at`), `league_memberships`,
and `push_subscriptions`. A member who has not subscribed gets no reminder.

## 2. The member journey, end to end

Do **not** attempt this by guessing the admin PIN. The lockout is durable —
`failed_login_count` and `locked_until` are profile columns, five attempts
locks the account for fifteen minutes, and locking the owner out before a
Saturday is a worse outcome than skipping the check. One failed probe on
2026-08-20 incremented the counter and had to be reset.

Instead mint a token with the application's own helper, inside the container,
and call the API over localhost. This exercises the real HTTP path — auth
middleware, routers, and the live odds provider — with no credentials involved:

```python
from src.auth import create_access_token
token = create_access_token(user.id, user.role)   # then call http://127.0.0.1:8080
```

Check `/api/v1/config`, `/leagues/mine`, the current slate, the gameweek list,
the combined coupon, `/me/cross-league-summary`, and results.

## 3. Odds coverage for the target Saturday

```bash
python .launch-private/weekend-fixtures.py 2026-08-22
```

Reports qualifying fixtures, how many are priced, and distinct priced
selections against the fifteen a full league needs. It reads the odds API only
and touches no bookmaker account.

## Snapshot — 2026-08-20, for Saturday 2026-08-22

| Check | Result |
| --- | --- |
| API | `33191ba2`, migration `015`, `/health` and `/health/ready` both 200, `db: ok` |
| Round | `the-coupon` GW3, **open**, **137 fixtures**, locks `2026-08-22 13:30 UTC` (14:30 London) |
| Slate through the API | 137 fixtures, **115 priced, 489 selections** |
| Wire format | `locks_at_utc: 2026-08-22T13:30:00Z` — the offset is present, so Batch 43 is live |
| `picks_open_at_utc` | `NULL` — no opening gate; picks are open now (the Batch 40 case) |
| Provider coverage | 134 qualifying 15:00 fixtures, 474 distinct priced selections |
| Fixture pool | 416 rows |
| RLS | 18/18 tables enabled **and** forced; no grants to `anon`/`authenticated`/`PUBLIC` |
| Football tables | 0 rows — provider is `none` by owner decision, tab is empty by design |
| **Members** | **1** (`Craig`, admin) — see below |

### The one thing that was not ready

**Production held a single member.** `roster.json` contains one player, so the
bootstrap is idempotent, has run, and matches production exactly — the gap is
that nobody has written down who the other fourteen are.

Two ways to close it:

1. **Share the app link.** Signup is public as of ADR 0008: a member creates
   their own account at `/register`, chooses their own PIN, and joins with an
   invite link or the join code. `the-coupon` is `private` with
   `max_members = 15`, which bounds the league rather than the number of
   accounts. This is the designed path and needs nothing from the owner beyond
   distributing the link.
2. **Extend `.launch-private/roster.json` and re-run `bootstrap-production.sh`.**
   Owner-only; needs the real names and PINs. Idempotent in the sense that it
   creates no duplicates, but **not** harmless: it rewrites `pin_hash` and clears
   `failed_login_count` and `locked_until` for every roster entry it lists, so a
   listed member who has since chosen their own PIN loses it. Members who
   registered themselves are not in the roster and are unaffected.

### Also noted

- A second league, `test`, exists and is `public_open` with its own 135-fixture
  round. Left alone by owner decision on 2026-08-20. It is discoverable and
  joinable — and since ADR 0008 opened signup on 2026-08-22, the population that
  can reach it is no longer "a real member if the roster ever grows" but anyone
  who creates an account. The 2026-08-20 decision was taken while account
  creation was closed; it is worth revisiting on that basis.
- The admin PIN is **not** the value in `roster.json` — a login attempt with it
  was refused, which means it has already been changed. That closes the
  "administrator PIN is a known value" follow-up `STATUS.md` carried.

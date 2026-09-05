import os
from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_SECRETS = {"change-me-access", "change-me-refresh"}
_MIN_SECRET_LEN = 32
#: Shortest value :meth:`Settings.secret_values` will hand the log redactor. Well below
#: `_MIN_SECRET_LEN` because provider API keys are not held to the JWT secrets' length
#: rule — odds-api.io and api-football both issue keys shorter than 32 characters.
_MIN_REDACTABLE_SECRET = 8


def _private_file_error(path_value: str, field_name: str) -> str | None:
    path = Path(path_value)
    if not path.is_absolute():
        return f"{field_name} must be an absolute path"
    if not path.is_file():
        return f"{field_name} does not identify a file"
    if not os.access(path, os.R_OK):
        return f"{field_name} is not readable"
    if path.stat().st_mode & 0o077:
        return f"{field_name} must not be accessible by group or other users"
    return None


class Environment(StrEnum):
    development = "development"
    staging = "staging"
    production = "production"


class OddsProviderName(StrEnum):
    """Which odds source the app runs against.

    ``oddsapi`` is production (ADR 0002). ``betfair`` is retained as a fallback but is
    geo-blocked from every region the deployment platform offers and never priced the
    Scottish lower divisions. ``fake`` serves canned data and is forbidden in production.
    """

    oddsapi = "oddsapi"
    betfair = "betfair"
    fake = "fake"


class FootballDataProviderName(StrEnum):
    """Which football-data source supplies tables, results and form (Batch 16).

    A second provider, independent of the odds one: odds-api.io publishes no standings.
    ``apifootball`` is api-sports.io (ADR 0003); ``fotmob`` is FotMob (ADR 0007), and is
    the only one of the two that carries the current season. ``fotmob`` needs **no key**
    — it authenticates nothing — so the production validator must not demand one for it.
    ``fake`` serves canned data and is forbidden in production. ``none`` is the default
    and turns *ingestion* off — the screens still read whatever is already in ``teams`` /
    ``matches`` / ``standings``, so an unconfigured deployment shows no football data
    rather than failing.

    ``none`` rather than ``apifootball`` is the default deliberately: production is
    already deployed and sealed, and defaulting to a provider whose key it does not hold
    would stop it starting.
    """

    apifootball = "apifootball"
    fotmob = "fotmob"
    fake = "fake"
    none = "none"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/the_coupon"

    # Auth
    jwt_access_secret: str
    jwt_refresh_secret: str

    # Web Push
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_contact_email: str = "admin@example.com"

    # Odds source. `oddsapi` (odds-api.io, priced by one bookmaker) is production;
    # see docs/adr/0002-replace-betfair-exchange-with-odds-api-io.md.
    odds_provider: OddsProviderName = OddsProviderName.oddsapi
    odds_api_key: str = ""
    odds_api_bookmaker: str = "Bet365"
    odds_api_base_url: str = "https://api.odds-api.io/v3"
    # How long a fetched price may be served from the process cache. `fetch_odds` runs in
    # the request path, so these are the only thing standing between the pick page and the
    # free plan's 100 requests/hour and 500/day.
    #
    # The arithmetic, using the measured launch Saturday: 131 qualifying fixtures batched
    # ten at a time is 14 requests per full sweep, so browsing costs `14 * 3600 / ttl` per
    # hour of continuous refreshing. At 300s that is 168/hour — over budget. At 900s it is
    # 56/hour.
    #
    # Batch 11 made the ceiling a function of how close lock is, because the two things a
    # price is used for want different freshness. Browsing the card tolerates a stale-ish
    # price; the price *frozen onto a pick* does not — and buying that freshness for the
    # one fixture being picked costs a single request instead of a sweep:
    #
    #   lock > 24h away   -> `odds_cache_ttl_seconds`      7200s ->  7/hour
    #   lock 6-24h away   -> half of it                    3600s -> 14/hour
    #   lock < 6h away    -> `odds_cache_near_ttl_seconds` 1800s -> 28/hour
    #   submitting a pick -> `odds_cache_pick_ttl_seconds`   60s -> 1 request per fixture
    #
    # The **daily** cap is what sets these, not the hourly one. 500/day minus the ~60 the
    # discovery job spends leaves 440 for odds, or 31 sweeps. A fully saturated day —
    # someone refreshing continuously for 24 hours — is 18 sweeps at the loose tiers plus
    # 12 in the final six hours: 30 sweeps, 420 requests, 480 with discovery. The tightest
    # hour is then 28/hour against a 100/hour allowance, so there is room to tighten the
    # near tier if the daily budget ever grows; there is none to tighten it today.
    #
    # `tests/test_request_budget.py` asserts this arithmetic against a real cache rather
    # than trusting this comment.
    odds_cache_ttl_seconds: int = 7200
    odds_cache_near_ttl_seconds: int = 1800
    odds_cache_pick_ttl_seconds: int = 60

    # ── What the absence of a price costs (Batch 114) ───────────────────────────
    #
    # The arithmetic above sizes the budget on 131 fixtures the bookmaker *prices*. On
    # 2026-09-05 an open round held 202, of which 103 — the FA Cup qualifying round, non-
    # league ties — Bet365 priced none. Those 103 cost 11 of every sweep's 21 requests and
    # rendered as rows no member could pick, and the plan was gone by 08:06 on a match
    # morning.
    #
    # A `None` entry used to expire on the same clock as a real price, so "this fixture has
    # no market" was re-bought every half hour. It is a far more durable fact than a price
    # is: a bookmaker that has not opened a market on a non-league cup tie will still not
    # have opened one in thirty minutes. Six hours is the ceiling for the in-process entry
    # and the floor for re-asking about a persisted marker (`fixtures.odds_unpriced_since_utc`,
    # revision 023) — long enough to take the 103 out of the hourly bill, short enough that a
    # market opened late on the morning of a match is found before that afternoon's lock.
    odds_cache_unpriced_ttl_seconds: int = 21600
    odds_unpriced_recheck_seconds: int = 21600

    # How long a `429` suppresses upstream calls. A rate limit says the quota is already
    # spent, so the one thing that cannot help is another request — and the pick path
    # retries by hand: `72204256` was refused twice inside one second by a member tapping
    # again, each tap a fresh call against an empty budget. Five minutes is shorter than
    # the hour a quota takes to roll over, deliberately: the counters below are an estimate
    # of the plan's own, and a cooldown longer than the recovery would keep serving stale
    # prices after the allowance came back.
    odds_rate_limited_cooldown_seconds: int = 300

    # The plan, as numbers the process can count against rather than a comment. Nothing
    # counted what had been spent, which is why an exhausted allowance and a five-hour-old
    # card looked identical from outside. These are the free plan's published limits; a
    # deployment on a larger plan raises them and the tiers above widen to match.
    odds_hourly_request_limit: int = 100
    odds_daily_request_limit: int = 500
    # The floor of the hourly allowance kept for the pick path. Browsing is a convenience
    # with no deadline; freezing a price is the one action that expires, so it must not be
    # starved by a card somebody left open. Fifty is `LEAGUE_MAX_MEMBERS`: a full league can
    # still take its picks in the hour when browsing has spent everything else.
    odds_pick_reserve_requests: int = 50

    # When the late slate pass runs, Europe/London, as a `CronTrigger` hour expression.
    #
    # It was pinned at `9,13` in `create_scheduler`. 13:00 London is ninety minutes before
    # the default 14:30 lock, so the pass spent ~30 requests in the hour members are hardest
    # to serve — and by then most of them have already picked, so the freshness was worth
    # less than the quota (owner decision, 2026-09-05). 11:00 keeps a late pass that can
    # still catch a postponement while leaving the pick peak alone.
    #
    # A setting rather than a literal because a cron a deployment cannot change without a
    # release is one nobody can move during an incident.
    odds_refresh_slate_hours: str = "9,11"

    # How many upcoming Saturdays the daily discovery job walks into `fixtures`. Fixture
    # discovery costs one request per UK competition (~30), so each extra Saturday is ~30
    # requests once a day — cheap, and it means a member picking on Tuesday already has a
    # full card rather than waiting for match day.
    slate_horizon_weeks: int = 2

    # ── Football data: tables, previous results, form (Batch 16) ────────────────
    #
    # A separate provider from the odds one, with a far smaller allowance: API-Football's
    # free plan is **100 requests/day** and **10 requests/minute**, against odds-api.io's
    # 500/day. Those two numbers decide the whole design — nothing here may run in the
    # request path, so ingestion writes `teams` / `matches` / `standings` on a schedule
    # and every screen reads those.
    #
    # The arithmetic, for the 30 UK competitions the slate carries: one catalogue request
    # per run (cached on the client), then one `/standings` and one `/fixtures` per
    # competition — 61 requests for a full daily sweep, against 100. The scheduled run
    # spaces competitions by 12 seconds so that two-request unit stays below 10/minute.
    # `football_competitions_per_run` is the guard: competitions are synced
    # least-recently-first, so a slate that grows past the cap rotates through rather than
    # starving its tail. `tests/test_football_data.py` asserts this against a counting
    # provider.
    football_data_provider: FootballDataProviderName = FootballDataProviderName.none
    football_api_key: str = ""
    football_api_base_url: str = "https://v3.football.api-sports.io"
    # Which season to ingest. `None` derives it from today (August-May, named by the
    # starting year), which is what a live deployment wants; an explicit value is for
    # backfilling a finished season, or for the canned data, which describes 2025-26.
    football_season: int | None = None
    football_competitions_per_run: int = 30
    football_competition_spacing_seconds: float = 12.0
    # How far back the scheduled top-up asks for results. Long enough to pick up a match
    # rearranged after the fact; the season backfill is what fills history.
    football_results_lookback_days: int = 30
    # How many recent matches make up a form line.
    football_form_matches: int = 5
    # How much of the results screen is served, in **match days** rather than rows
    # (Batch 71).
    #
    # It was `football_recent_results_limit: int = 20`, and the comment beside it said
    # "how many results a competition shows" — which was never what it did. It was a flat
    # cap across every pooled competition at once, and the screen groups by day and then
    # by competition, so a busy Saturday simply fell off the end of it. Measured against
    # production on 2026-08-23: 567 finished matches across 18 competitions, 145 of them
    # on Saturday 2026-08-22 across 17 competitions, of which the newest twenty covered
    # **six**. Eleven divisions vanished, which is exactly the "partially there" a member
    # reported.
    #
    # Days rather than rows because the unit of the answer should match the unit of the
    # display. Three covers a whole weekend — Friday night through Sunday — which is what
    # "previous results" means to somebody who plays a Saturday game. They are the three
    # most recent days that *have* results, not three calendar days, so a midweek gap
    # cannot return an empty screen.
    football_results_days: int = 3
    # A backstop, not a page size. Nothing observed comes close to it; it is here so a
    # pathological ingestion cannot turn one request into an unbounded response.
    football_results_max_rows: int = 400
    # How many competitions one live-score poll may walk (Batch 72). FotMob needs no key
    # and has no rate limit to protect, so this is politeness and a blast-radius bound
    # rather than a budget: a poll only ever runs while some league has a round in play,
    # and a round draws on a handful of divisions, not thirty.
    live_scores_competitions_per_run: int = 12

    # Betfair Exchange API — only read when `odds_provider` is `betfair`. Production
    # uses non-interactive certificate login.
    bf_app_key: str = ""
    bf_user: str = ""
    bf_pass: str = ""
    bf_cert_file: str = ""
    bf_key_file: str = ""
    # Deprecated: superseded by ODDS_PROVIDER=fake. Retained so environments sealed
    # before ADR 0002 keep serving canned data instead of silently switching to a live
    # provider they have no key for. Still refused in production.
    bf_fake_mode: bool = False

    # App
    #: How many reverse proxies in front of this app are ours, for reading
    #: ``X-Forwarded-For``. Railway puts exactly one edge in front of the service, so the
    #: rightmost entry is the address it observed and everything left of it is
    #: caller-supplied. Raise this only if a CDN is added in front of Railway; lowering it
    #: below 1 is meaningless and is clamped in ``rate_limit.client_address``.
    trusted_proxy_count: int = 1
    frontend_origin: str = "http://localhost:5173"
    log_level: str = "INFO"
    # Unknown strings are rejected by the enum (fail-closed).
    environment: Environment | None = Field(default=None)
    # Railway injects this into the deploy env so /health can expose the running SHA.
    railway_git_commit_sha: str | None = None

    # Backup
    backup_dir: str = "/tmp/the_coupon_backups"

    # Background scheduler (APScheduler) — disable in tests / one-off scripts.
    scheduler_enabled: bool = True

    # Public self-serve signup (owner's 2026-08-22 decision). On by default, because a
    # shared link that dead-ends at a sign-in form is the defect this replaced. Set
    # PUBLIC_SIGNUP_ENABLED=false to close registration without a deploy — existing
    # members are unaffected and `POST /auth/register` starts answering 403. There is no
    # email verification anywhere in this product, so this switch is the only way to stop
    # account creation once it starts being abused.
    public_signup_enabled: bool = True

    # Profile pictures (Batch 42). The cap is enforced before any byte is stored, and is
    # deliberately small: an avatar is displayed at a few dozen pixels, so anything larger
    # is a payload rather than a picture.
    avatar_max_bytes: int = 2 * 1024 * 1024
    # Which backend stores them (Batch 44): "none" or "supabase". Defaults to "none", so
    # a deployment that has not provisioned a bucket keeps answering 503 and the web app
    # keeps its upload control unmounted. Turning it on is one variable plus the two
    # below — see docs/runbooks/avatar-storage.md.
    avatar_storage: str = "none"
    avatar_bucket: str = "avatars"
    # Supabase project REST base (https://<ref>.supabase.co) and its service-role key.
    # The key bypasses RLS by design and is why the bucket's policies are written
    # explicitly rather than left to defaults; it never reaches a browser.
    supabase_url: str = ""
    supabase_service_key: str = ""

    def secret_values(self) -> tuple[str, ...]:
        """Every configured secret whose literal value must never reach a log line.

        Fed to :func:`~src.logging_config.configure_logging`, which redacts these from
        rendered output whatever produced them. That is deliberately broader than the
        one leak it was written for — odds-api.io takes its key as a query parameter
        (``odds_api.py``), so any library that logs a request URL leaks it, and httpx
        did exactly that at INFO for months.

        Values shorter than :data:`_MIN_REDACTABLE_SECRET` are excluded. A short string
        appears inside unrelated log text by coincidence, and redacting it would corrupt
        lines rather than protect anything; no real credential here is that short. An
        unset secret is the empty string and is excluded by the same rule.

        Sorted longest first so that a secret containing another as a substring is
        replaced before its own substring can partially mask it.
        """
        candidates = (
            self.jwt_access_secret,
            self.jwt_refresh_secret,
            self.vapid_private_key,
            self.odds_api_key,
            self.football_api_key,
            self.bf_app_key,
            self.bf_pass,
            self.supabase_service_key,
        )
        unique = {value for value in candidates if len(value) >= _MIN_REDACTABLE_SECRET}
        return tuple(sorted(unique, key=len, reverse=True))

    @model_validator(mode="after")
    def _apply_deprecated_fake_mode(self) -> "Settings":
        """Honour a pre-ADR-0002 ``BF_FAKE_MODE=true`` as ``ODDS_PROVIDER=fake``.

        Staging was sealed with ``BF_FAKE_MODE`` before the odds source changed. Ignoring
        it would point staging at a live provider it has no key for, so it still selects
        the fake — but only when ``ODDS_PROVIDER`` was not set explicitly, and never in
        production, where the check below refuses it outright.
        """
        if self.bf_fake_mode and "odds_provider" not in self.model_fields_set:
            self.odds_provider = OddsProviderName.fake
        return self

    @model_validator(mode="after")
    def _reject_weak_secrets_in_prod(self) -> "Settings":
        if self.environment is None:
            if self.model_fields_set and (
                "environment" in self.model_fields_set
                or any(
                    key in self.model_fields_set
                    for key in ("jwt_access_secret", "jwt_refresh_secret")
                )
            ):
                self.environment = Environment.development
                return self
            raise ValueError("ENVIRONMENT must be set explicitly")
        if self.environment == Environment.development:
            return self
        errors: list[str] = []
        if self.jwt_access_secret in _PLACEHOLDER_SECRETS:
            errors.append("jwt_access_secret is a placeholder value")
        if self.jwt_refresh_secret in _PLACEHOLDER_SECRETS:
            errors.append("jwt_refresh_secret is a placeholder value")
        if len(self.jwt_access_secret) < _MIN_SECRET_LEN:
            errors.append(f"jwt_access_secret must be at least {_MIN_SECRET_LEN} characters")
        if len(self.jwt_refresh_secret) < _MIN_SECRET_LEN:
            errors.append(f"jwt_refresh_secret must be at least {_MIN_SECRET_LEN} characters")
        if self.jwt_access_secret == self.jwt_refresh_secret:
            errors.append("jwt_access_secret and jwt_refresh_secret must be different")
        if not self.vapid_public_key:
            errors.append("vapid_public_key is empty")
        if not self.vapid_private_key:
            errors.append("vapid_private_key is empty")
        if not self.database_url:
            errors.append("database_url is empty")
        if not self.frontend_origin or self.frontend_origin.startswith("http://localhost"):
            errors.append("frontend_origin must not be empty or localhost in production")
        if self.environment == Environment.production:
            if self.bf_fake_mode:
                errors.append("bf_fake_mode is forbidden in production")
            if self.odds_provider == OddsProviderName.fake:
                errors.append("odds_provider 'fake' is forbidden in production")
            if self.football_data_provider == FootballDataProviderName.fake:
                errors.append("football_data_provider 'fake' is forbidden in production")
            # `none` needs no key — it is the default, and it only turns ingestion off.
            if (
                self.football_data_provider == FootballDataProviderName.apifootball
                and not self.football_api_key
            ):
                errors.append("football_api_key is empty")
            # Each provider's credentials are required only when it is the one selected.
            # Betfair's certificate pair stopped being a production requirement with
            # ADR 0002; demanding it under odds-api.io would block a valid deployment.
            if self.odds_provider == OddsProviderName.oddsapi:
                if not self.odds_api_key:
                    errors.append("odds_api_key is empty")
                if not self.odds_api_bookmaker:
                    errors.append("odds_api_bookmaker is empty")
            if self.odds_provider == OddsProviderName.betfair:
                if not self.bf_app_key:
                    errors.append("bf_app_key is empty")
                if not self.bf_user:
                    errors.append("bf_user is empty")
                if not self.bf_pass:
                    errors.append("bf_pass is empty")
                if not self.bf_cert_file:
                    errors.append("bf_cert_file is empty")
                else:
                    cert_error = _private_file_error(self.bf_cert_file, "bf_cert_file")
                    if cert_error:
                        errors.append(cert_error)
                if not self.bf_key_file:
                    errors.append("bf_key_file is empty")
                else:
                    key_error = _private_file_error(self.bf_key_file, "bf_key_file")
                    if key_error:
                        errors.append(key_error)
        if errors:
            raise ValueError("Refusing to start with weak/missing secrets: " + "; ".join(errors))
        return self


settings = Settings()  # type: ignore[call-arg]  # env vars supply required fields at runtime


def docs_urls(environment: Environment) -> dict[str, str | None]:
    """OpenAPI/Swagger/ReDoc URLs for the app — disabled (None) in production.

    A private, invite-only app shouldn't expose its full API schema to anonymous
    callers, so the three doc routes are turned off in production; dev/staging
    keep them for convenience. (Review finding P3-7.)
    """
    if environment == Environment.production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {
        "docs_url": "/api/docs",
        "redoc_url": "/api/redoc",
        "openapi_url": "/api/openapi.json",
    }

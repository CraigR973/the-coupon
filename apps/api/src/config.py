import os
from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_SECRETS = {"change-me-access", "change-me-refresh"}
_MIN_SECRET_LEN = 32


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
    # the request path, so this is the only thing standing between the pick page and the
    # free plan's 100 requests/hour and 500/day.
    #
    # The arithmetic, using the measured launch Saturday: 131 qualifying fixtures batched
    # ten at a time is 14 requests per full refresh, so the hourly cost is
    # `14 * 3600 / ttl`. At 300s that is 168/hour — over budget. At 900s it is 56/hour,
    # and a price frozen at pick time is never more than fifteen minutes stale, which is
    # immaterial for pre-match lower-league football.
    #
    # The *daily* cap is the tighter one under sustained load: 56/hour for ten hours of
    # continuous Saturday refreshing is 560, above the 500/day allowance. Raise this if
    # the provider starts returning 429s on a match day.
    odds_cache_ttl_seconds: int = 900

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

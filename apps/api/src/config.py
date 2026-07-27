from enum import StrEnum

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_SECRETS = {"change-me-access", "change-me-refresh"}
_MIN_SECRET_LEN = 32


class Environment(StrEnum):
    development = "development"
    staging = "staging"
    production = "production"


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

    # Betfair Exchange API (odds source). Interactive login — no cert needed.
    # Empty by default so tests/dev run without a live session; Betfair.from_settings
    # raises when a caller needs the real client but these are unset.
    bf_app_key: str = ""
    bf_user: str = ""
    bf_pass: str = ""
    bf_cert_file: str = ""
    bf_key_file: str = ""
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
            if not self.bf_app_key:
                errors.append("bf_app_key is empty")
            if not self.bf_user:
                errors.append("bf_user is empty")
            if not self.bf_pass:
                errors.append("bf_pass is empty")
            if not self.bf_cert_file:
                errors.append("bf_cert_file is empty")
            if not self.bf_key_file:
                errors.append("bf_key_file is empty")
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

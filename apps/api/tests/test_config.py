"""Tests for Settings: production fail-closed validation of required secrets."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import Environment, OddsProviderName, Settings, docs_urls


def _build_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Construct Settings from a valid production baseline, overriding per test.

    Every field the prod validator inspects is supplied as an init kwarg so the
    result is deterministic regardless of the ambient .env / environment. The baseline
    runs on odds-api.io, which is what production actually uses (ADR 0002).
    """
    params: dict[str, object] = {
        "environment": Environment.production,
        "jwt_access_secret": "a" * 32,
        "jwt_refresh_secret": "b" * 32,
        "vapid_public_key": "vapid-public",
        "vapid_private_key": "vapid-private",
        "database_url": "postgresql+asyncpg://u:p@host:5432/db",
        "frontend_origin": "https://app.example.com",
        "odds_provider": OddsProviderName.oddsapi,
        "odds_api_key": "odds-api-key",
        "odds_api_bookmaker": "Bet365",
    }
    params.update(overrides)
    return Settings(**params)  # type: ignore[arg-type]


def _build_betfair_settings(tmp_path: Path, **overrides: object) -> Settings:
    """A production baseline that has selected the Exchange as its odds source."""
    cert_path = tmp_path / "betfair.crt"
    key_path = tmp_path / "betfair.key"
    cert_path.write_text("test certificate", encoding="utf-8")
    key_path.write_text("test private key", encoding="utf-8")
    cert_path.chmod(0o600)
    key_path.chmod(0o600)
    params: dict[str, object] = {
        "odds_provider": OddsProviderName.betfair,
        "bf_app_key": "betfair-app-key",
        "bf_user": "betfair-user",
        "bf_pass": "betfair-pass",
        "bf_cert_file": str(cert_path),
        "bf_key_file": str(key_path),
    }
    params.update(overrides)
    return _build_settings(tmp_path, **params)


def test_valid_production_settings_construct(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    assert settings.environment == Environment.production


def test_production_does_not_require_removed_template_services(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    assert settings.environment == Environment.production


def test_production_rejects_short_jwt_secret(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="jwt_access_secret must be at least"):
        _build_settings(tmp_path, jwt_access_secret="short")


def test_production_rejects_identical_jwt_secrets(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be different"):
        _build_settings(
            tmp_path,
            jwt_access_secret="x" * 40,
            jwt_refresh_secret="x" * 40,
        )


def test_development_allows_weak_jwt_secrets(tmp_path: Path) -> None:
    # The validator is fully skipped in development, so a short/identical pair is fine.
    settings = _build_settings(
        tmp_path,
        environment=Environment.development,
        jwt_access_secret="dev",
        jwt_refresh_secret="dev",
    )
    assert settings.jwt_access_secret == "dev"


def test_production_rejects_fake_betfair_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bf_fake_mode is forbidden"):
        _build_settings(tmp_path, bf_fake_mode=True)


# ── ADR 0002: the odds provider decides which credentials production requires ──


def test_production_requires_an_odds_api_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="odds_api_key is empty"):
        _build_settings(tmp_path, odds_api_key="")


def test_production_requires_a_bookmaker(tmp_path: Path) -> None:
    """One bookmaker prices everything, so an empty selection is not a valid config."""
    with pytest.raises(ValueError, match="odds_api_bookmaker is empty"):
        _build_settings(tmp_path, odds_api_bookmaker="")


def test_production_rejects_the_fake_provider(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="odds_provider 'fake' is forbidden"):
        _build_settings(tmp_path, odds_provider=OddsProviderName.fake)


def test_production_on_odds_api_does_not_require_betfair_credentials(tmp_path: Path) -> None:
    """The Exchange certificate stopped being a production requirement with ADR 0002.

    Demanding it under odds-api.io would block a valid deployment — and production has no
    Betfair certificate, because the Exchange refuses the login from every region the
    platform offers.
    """
    settings = _build_settings(tmp_path)
    assert settings.bf_app_key == ""
    assert settings.bf_cert_file == ""


def test_production_on_betfair_still_validates_its_credentials(tmp_path: Path) -> None:
    settings = _build_betfair_settings(tmp_path)
    assert settings.odds_provider is OddsProviderName.betfair

    with pytest.raises(ValueError, match="bf_app_key is empty"):
        _build_betfair_settings(tmp_path, bf_app_key="")


def test_production_rejects_missing_betfair_certificate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bf_cert_file does not identify a file"):
        _build_betfair_settings(tmp_path, bf_cert_file=str(tmp_path / "missing.crt"))


def test_production_rejects_permissive_betfair_private_key(tmp_path: Path) -> None:
    key_path = tmp_path / "permissive.key"
    key_path.write_text("test private key", encoding="utf-8")
    key_path.chmod(0o644)

    with pytest.raises(ValueError, match="accessible by group or other"):
        _build_betfair_settings(tmp_path, bf_key_file=str(key_path))


def _staging_settings(**overrides: object) -> Settings:
    """A staging baseline that leaves ODDS_PROVIDER unset unless a test sets it."""
    params: dict[str, object] = {
        "environment": Environment.staging,
        "jwt_access_secret": "a" * 32,
        "jwt_refresh_secret": "b" * 32,
        "vapid_public_key": "vapid-public",
        "vapid_private_key": "vapid-private",
        "database_url": "postgresql+asyncpg://u:p@host:5432/db",
        "frontend_origin": "https://staging.example.com",
    }
    params.update(overrides)
    return Settings(**params)  # type: ignore[arg-type]


def test_deprecated_fake_mode_still_selects_the_fake_provider() -> None:
    """Staging was sealed with BF_FAKE_MODE before the odds source changed.

    Ignoring it would silently point staging at a live provider it has no key for.
    """
    assert _staging_settings(bf_fake_mode=True).odds_provider is OddsProviderName.fake


def test_explicit_provider_wins_over_deprecated_fake_mode() -> None:
    settings = _staging_settings(
        bf_fake_mode=True, odds_provider=OddsProviderName.oddsapi, odds_api_key="k"
    )
    assert settings.odds_provider is OddsProviderName.oddsapi


def test_odds_api_is_the_default_provider() -> None:
    assert _staging_settings().odds_provider is OddsProviderName.oddsapi


def test_docs_urls_disabled_in_production() -> None:
    assert docs_urls(Environment.production) == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


def test_docs_urls_enabled_outside_production() -> None:
    urls = docs_urls(Environment.development)
    assert urls["docs_url"] == "/api/docs"
    assert urls["redoc_url"] == "/api/redoc"
    assert urls["openapi_url"] == "/api/openapi.json"


# ── Secrets handed to the log redactor ────────────────────────────────────────


def test_secret_values_collects_every_configured_credential(tmp_path: Path) -> None:
    settings = _build_settings(
        tmp_path,
        odds_api_key="odds-api-key-long-enough",
        football_api_key="football-api-key-long-enough",
    )
    values = settings.secret_values()

    assert "odds-api-key-long-enough" in values
    assert "football-api-key-long-enough" in values
    assert "a" * 32 in values  # jwt_access_secret
    assert "b" * 32 in values  # jwt_refresh_secret


def test_secret_values_excludes_unset_and_short_values(tmp_path: Path) -> None:
    """A short or empty secret must not be redacted.

    An unset credential is `""`, and replacing the empty string would rewrite every
    character boundary in the line. A very short one would blank out unrelated words
    that happen to contain it. Neither is a credential worth protecting anyway.
    """
    settings = _build_settings(tmp_path, odds_api_key="short", football_api_key="")
    values = settings.secret_values()

    assert "" not in values
    assert "short" not in values
    assert all(len(value) >= 8 for value in values)


def test_secret_values_orders_longest_first(tmp_path: Path) -> None:
    """A secret containing another as a substring must be replaced first.

    Redacting the shorter one first would leave the longer one's remaining characters
    on the line — a partial secret, which reads as safe and is not.
    """
    settings = _build_settings(
        tmp_path,
        odds_api_key="shared-prefix-secret",
        football_api_key="shared-prefix-secret-with-more",
    )
    values = settings.secret_values()

    assert list(values) == sorted(values, key=len, reverse=True)

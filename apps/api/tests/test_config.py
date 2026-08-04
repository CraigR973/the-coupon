"""Tests for Settings: production fail-closed validation of required secrets."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import Environment, Settings, docs_urls


def _build_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Construct Settings from a valid production baseline, overriding per test.

    Every field the prod validator inspects is supplied as an init kwarg so the
    result is deterministic regardless of the ambient .env / environment.
    """
    cert_path = tmp_path / "betfair.crt"
    key_path = tmp_path / "betfair.key"
    cert_path.write_text("test certificate", encoding="utf-8")
    key_path.write_text("test private key", encoding="utf-8")
    cert_path.chmod(0o600)
    key_path.chmod(0o600)
    params: dict[str, object] = {
        "environment": Environment.production,
        "jwt_access_secret": "a" * 32,
        "jwt_refresh_secret": "b" * 32,
        "vapid_public_key": "vapid-public",
        "vapid_private_key": "vapid-private",
        "database_url": "postgresql+asyncpg://u:p@host:5432/db",
        "frontend_origin": "https://app.example.com",
        "bf_app_key": "betfair-app-key",
        "bf_user": "betfair-user",
        "bf_pass": "betfair-pass",
        "bf_cert_file": str(cert_path),
        "bf_key_file": str(key_path),
    }
    params.update(overrides)
    return Settings(**params)  # type: ignore[arg-type]


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


def test_production_rejects_missing_betfair_certificate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bf_cert_file does not identify a file"):
        _build_settings(tmp_path, bf_cert_file=str(tmp_path / "missing.crt"))


def test_production_rejects_permissive_betfair_private_key(tmp_path: Path) -> None:
    key_path = tmp_path / "permissive.key"
    key_path.write_text("test private key", encoding="utf-8")
    key_path.chmod(0o644)

    with pytest.raises(ValueError, match="accessible by group or other"):
        _build_settings(tmp_path, bf_key_file=str(key_path))


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

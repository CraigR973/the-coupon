from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.runtime_secrets import materialize_betfair_certificate

_CERTIFICATE = b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n"
_PRIVATE_KEY = b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n"


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _betfair_production_env(cert_path: Path, key_path: Path) -> dict[str, str]:
    """A production environment that has selected the Exchange as its odds source."""
    return {
        "ENVIRONMENT": "production",
        "ODDS_PROVIDER": "betfair",
        "BF_CERT_FILE": str(cert_path),
        "BF_KEY_FILE": str(key_path),
        "BF_CERT_PEM_B64": _encoded(_CERTIFICATE),
        "BF_KEY_PEM_B64": _encoded(_PRIVATE_KEY),
    }


def test_materializes_private_production_files(tmp_path: Path) -> None:
    cert_path = tmp_path / "runtime" / "betfair.crt"
    key_path = tmp_path / "runtime" / "betfair.key"
    materialize_betfair_certificate(
        _betfair_production_env(cert_path, key_path),
        expected_cert_path=cert_path,
        expected_key_path=key_path,
    )

    assert cert_path.read_bytes() == _CERTIFICATE
    assert key_path.read_bytes() == _PRIVATE_KEY
    assert cert_path.stat().st_mode & 0o777 == 0o600
    assert key_path.stat().st_mode & 0o777 == 0o600
    assert cert_path.parent.stat().st_mode & 0o777 == 0o700


def test_production_rejects_missing_certificate_value(tmp_path: Path) -> None:
    cert_path = tmp_path / "betfair.crt"
    key_path = tmp_path / "betfair.key"
    with pytest.raises(RuntimeError, match="requires both"):
        materialize_betfair_certificate(
            {
                "ENVIRONMENT": "production",
                "ODDS_PROVIDER": "betfair",
                "BF_CERT_FILE": str(cert_path),
                "BF_KEY_FILE": str(key_path),
            },
            expected_cert_path=cert_path,
            expected_key_path=key_path,
        )


def test_nonproduction_rejects_certificate_material(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="only in production"):
        materialize_betfair_certificate(
            {
                "ENVIRONMENT": "staging",
                "BF_CERT_PEM_B64": _encoded(_CERTIFICATE),
            },
            expected_cert_path=tmp_path / "betfair.crt",
            expected_key_path=tmp_path / "betfair.key",
        )


def test_rejects_unexpected_runtime_paths(tmp_path: Path) -> None:
    cert_path = tmp_path / "expected.crt"
    key_path = tmp_path / "expected.key"
    env = _betfair_production_env(cert_path, key_path)
    env["BF_CERT_FILE"] = str(tmp_path / "other.crt")
    with pytest.raises(RuntimeError, match="BF_CERT_FILE must be"):
        materialize_betfair_certificate(
            env, expected_cert_path=cert_path, expected_key_path=key_path
        )


# ── ADR 0002: the certificate is only needed when the Exchange is the source ───


def test_production_on_odds_api_needs_no_certificate(tmp_path: Path) -> None:
    """The default provider authenticates with a key, so production writes nothing.

    Before ADR 0002 this raised: production demanded the BF_* PEM pair unconditionally,
    which would now block a perfectly valid odds-api.io deployment.
    """
    cert_path = tmp_path / "betfair.crt"
    key_path = tmp_path / "betfair.key"

    materialize_betfair_certificate(
        {"ENVIRONMENT": "production", "ODDS_PROVIDER": "oddsapi"},
        expected_cert_path=cert_path,
        expected_key_path=key_path,
    )
    # An unset ODDS_PROVIDER means the odds-api.io default, not Betfair.
    materialize_betfair_certificate(
        {"ENVIRONMENT": "production"},
        expected_cert_path=cert_path,
        expected_key_path=key_path,
    )

    assert not cert_path.exists()
    assert not key_path.exists()


def test_production_on_betfair_still_materializes(tmp_path: Path) -> None:
    cert_path = tmp_path / "runtime" / "betfair.crt"
    key_path = tmp_path / "runtime" / "betfair.key"

    materialize_betfair_certificate(
        _betfair_production_env(cert_path, key_path),
        expected_cert_path=cert_path,
        expected_key_path=key_path,
    )

    assert cert_path.read_bytes() == _CERTIFICATE

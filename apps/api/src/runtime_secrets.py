"""Materialize production-only runtime files from sealed environment values."""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Mapping
from pathlib import Path

_CERT_PATH = Path("/tmp/the_coupon_secrets/betfair-client.crt")
_KEY_PATH = Path("/tmp/the_coupon_secrets/betfair-client.key")
_CERT_VALUE_ENV = "BF_CERT_PEM_B64"
_KEY_VALUE_ENV = "BF_KEY_PEM_B64"


def _decode_pem(value: str, *, variable_name: str, marker: bytes) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError(f"{variable_name} must contain valid base64") from exc
    if marker not in decoded:
        raise RuntimeError(f"{variable_name} does not contain the expected PEM data")
    return decoded


def _write_private_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def materialize_betfair_certificate(
    environ: Mapping[str, str] | None = None,
    *,
    expected_cert_path: Path = _CERT_PATH,
    expected_key_path: Path = _KEY_PATH,
) -> None:
    values = os.environ if environ is None else environ
    environment = values.get("ENVIRONMENT", "")
    cert_value = values.get(_CERT_VALUE_ENV, "")
    key_value = values.get(_KEY_VALUE_ENV, "")

    if environment != "production":
        if cert_value or key_value:
            raise RuntimeError("Betfair certificate material is allowed only in production")
        return

    configured_cert_path = values.get("BF_CERT_FILE", "")
    configured_key_path = values.get("BF_KEY_FILE", "")
    if configured_cert_path != str(expected_cert_path):
        raise RuntimeError(f"BF_CERT_FILE must be {expected_cert_path}")
    if configured_key_path != str(expected_key_path):
        raise RuntimeError(f"BF_KEY_FILE must be {expected_key_path}")
    if not cert_value or not key_value:
        raise RuntimeError(f"Production requires both {_CERT_VALUE_ENV} and {_KEY_VALUE_ENV}")

    certificate = _decode_pem(
        cert_value,
        variable_name=_CERT_VALUE_ENV,
        marker=b"-----BEGIN CERTIFICATE-----",
    )
    private_key = _decode_pem(
        key_value,
        variable_name=_KEY_VALUE_ENV,
        marker=b"-----BEGIN ",
    )
    if b"PRIVATE KEY-----" not in private_key:
        raise RuntimeError(f"{_KEY_VALUE_ENV} does not contain a private key")

    _write_private_file(expected_cert_path, certificate)
    _write_private_file(expected_key_path, private_key)


if __name__ == "__main__":
    materialize_betfair_certificate()

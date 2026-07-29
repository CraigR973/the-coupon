"""Tests for backup helpers — the password is kept out of the pg_dump argv (P3-6)."""

from __future__ import annotations

from src.services.backup import _pg_dsn, _pg_password


def test_pg_dsn_strips_password_and_converts_scheme() -> None:
    dsn = _pg_dsn("postgresql+asyncpg://app:s3cr3t@db.example.com:5432/appdb")
    assert dsn == "postgresql://app@db.example.com:5432/appdb"
    assert "s3cr3t" not in dsn


def test_pg_dsn_preserves_query_params() -> None:
    dsn = _pg_dsn("postgresql+asyncpg://app:pw@db:5432/appdb?sslmode=require")
    assert dsn == "postgresql://app@db:5432/appdb?sslmode=require"
    assert "pw" not in dsn


def test_pg_dsn_maps_asyncpg_ssl_to_libpq_sslmode() -> None:
    dsn = _pg_dsn("postgresql+asyncpg://app:pw@db:5432/appdb?ssl=require")
    assert dsn == "postgresql://app@db:5432/appdb?sslmode=require"


def test_pg_dsn_prefers_explicit_sslmode() -> None:
    dsn = _pg_dsn("postgresql+asyncpg://app:pw@db:5432/appdb?ssl=require&sslmode=verify-full")
    assert dsn == "postgresql://app@db:5432/appdb?sslmode=verify-full"


def test_pg_dsn_brackets_ipv6_hosts() -> None:
    dsn = _pg_dsn("postgresql+asyncpg://app:pw@[2001:db8::1]:5432/appdb?ssl=require")
    assert dsn == "postgresql://app@[2001:db8::1]:5432/appdb?sslmode=require"


def test_pg_password_extracts_and_url_decodes() -> None:
    # %40 -> @, %3A -> : : the env var must carry the decoded password.
    url = "postgresql+asyncpg://app:p%40ss%3Aword@db.example.com:5432/appdb"
    assert _pg_password(url) == "p@ss:word"


def test_pg_helpers_handle_missing_password() -> None:
    url = "postgresql+asyncpg://app@localhost/appdb"
    assert _pg_password(url) is None
    assert _pg_dsn(url) == "postgresql://app@localhost/appdb"

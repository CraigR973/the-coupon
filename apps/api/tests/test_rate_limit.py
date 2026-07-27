import json

from starlette.requests import Request

from src.rate_limit import client_address, login_key


def _request(*, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": headers or [],
            "client": ("10.0.0.10", 12345),
        }
    )


def test_client_address_prefers_first_forwarded_for_ip() -> None:
    request = _request(headers=[(b"x-forwarded-for", b"203.0.113.9, 10.0.0.10")])

    assert client_address(request) == "203.0.113.9"


def test_login_key_uses_forwarded_ip_and_display_name() -> None:
    request = _request(headers=[(b"x-forwarded-for", b"203.0.113.9")])
    request._body = json.dumps({"display_name": "Craig"}).encode()  # type: ignore[attr-defined]

    assert login_key(request) == "login:craig:203.0.113.9"

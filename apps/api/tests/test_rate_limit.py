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


def test_client_address_reads_the_hop_the_trusted_proxy_wrote() -> None:
    """The rightmost entry, not the leftmost.

    ``X-Forwarded-For`` is ``client, proxy1, proxy2``: each proxy *appends* the address it
    was contacted from, so with one trusted proxy in front (Railway) the last entry is the
    one our own infrastructure observed. This asserted the first entry until Batch 58,
    which is the half of the header a caller writes.
    """
    request = _request(headers=[(b"x-forwarded-for", b"203.0.113.9, 10.0.0.10")])

    assert client_address(request) == "10.0.0.10"


def test_a_spoofed_forwarded_for_cannot_buy_a_fresh_bucket() -> None:
    """The bug this fixes: rotate the header, get a new rate-limit key every request.

    Every IP-keyed limit in the app hung off this — login's 5/15 minutes,
    pin/reset-request's 3/hour, the shared provider budgets. All of them were bypassable
    by anyone who thought to send their own header.
    """
    keys = {
        client_address(_request(headers=[(b"x-forwarded-for", f"{spoof}, 10.0.0.10".encode())]))
        for spoof in ("1.1.1.1", "2.2.2.2", "3.3.3.3", "198.51.100.7")
    }

    assert keys == {"10.0.0.10"}, "a caller-chosen prefix must not change the key"


def test_client_address_falls_back_to_the_peer_without_the_header() -> None:
    assert client_address(_request()) == "10.0.0.10"


def test_a_header_shorter_than_the_trusted_depth_uses_what_it_has() -> None:
    """One entry with one trusted proxy is the proxy's own view — take it, don't index past."""
    request = _request(headers=[(b"x-forwarded-for", b"203.0.113.9")])

    assert client_address(request) == "203.0.113.9"


def test_login_key_uses_forwarded_ip_and_display_name() -> None:
    request = _request(headers=[(b"x-forwarded-for", b"203.0.113.9")])
    request._body = json.dumps({"display_name": "Craig"}).encode()  # type: ignore[attr-defined]

    assert login_key(request) == "login:craig:203.0.113.9"


def test_login_key_is_stable_under_a_spoofed_prefix() -> None:
    """The whole point, at the layer that actually guards PIN guessing."""
    first = _request(headers=[(b"x-forwarded-for", b"1.1.1.1, 10.0.0.10")])
    first._body = json.dumps({"display_name": "Craig"}).encode()  # type: ignore[attr-defined]
    second = _request(headers=[(b"x-forwarded-for", b"2.2.2.2, 10.0.0.10")])
    second._body = json.dumps({"display_name": "Craig"}).encode()  # type: ignore[attr-defined]

    assert login_key(first) == login_key(second) == "login:craig:10.0.0.10"

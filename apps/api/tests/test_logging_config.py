import io
import logging
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import structlog

from src.logging_config import REDACTED, configure_logging
from src.services.odds_api import DEFAULT_BASE_URL, OddsApiProvider

#: Shaped like a real odds-api.io key (64 hex characters) so the test exercises the same
#: length and alphabet the live one has, without being a credential.
LIVE_SHAPED_KEY = "0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9"


@contextmanager
def _configured(*secrets: str) -> Iterator[io.StringIO]:
    """`configure_logging` applied for the duration, with its output captured.

    Restores the root handlers and every level this touches, because the configuration
    is process-global and a leaked handler would redirect a later test's output.
    """
    root = logging.getLogger()
    original_handlers = root.handlers
    original_level = root.level
    original_httpx_level = logging.getLogger("httpx").level
    try:
        configure_logging("INFO", secrets)
        stream = io.StringIO()
        root.handlers[0].setStream(stream)
        yield stream
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)
        logging.getLogger("httpx").setLevel(original_httpx_level)


def test_configure_logging_renders_exception_tracebacks() -> None:
    """log.exception() must emit the traceback, not a bare exc_info=true."""
    with _configured() as stream:
        log = structlog.get_logger("test.logging_config")
        try:
            raise ValueError("boom-marker-42")
        except ValueError:
            log.exception("operation failed")

        output = stream.getvalue()

    assert "operation failed" in output
    assert "boom-marker-42" in output
    assert "Traceback" in output


def test_a_secret_is_redacted_wherever_it_sits_in_the_line() -> None:
    """Message text, keyword value, and nested structure are all covered.

    Redaction happens at the renderer, so the three cases are one mechanism rather than
    three — this asserts that rather than trusting it.
    """
    with _configured(LIVE_SHAPED_KEY) as stream:
        log = structlog.get_logger("test.logging_config")
        log.info(f"calling https://api.odds-api.io/v3/leagues?apiKey={LIVE_SHAPED_KEY}")
        log.info("with a keyword", api_key=LIVE_SHAPED_KEY)
        log.info("nested", payload={"auth": {"key": LIVE_SHAPED_KEY}})

        output = stream.getvalue()

    assert LIVE_SHAPED_KEY not in output
    assert output.count(REDACTED) == 3


def test_a_third_party_logger_cannot_publish_a_secret() -> None:
    """The redactor is not structlog-specific.

    The leak this batch fixes came from httpx, which knows nothing about this
    application's logging conventions. Anything reaching the root handler is covered.
    """
    with _configured(LIVE_SHAPED_KEY) as stream:
        logging.getLogger("some.vendor.client").warning(
            "HTTP Request: GET https://api.odds-api.io/v3/leagues?apiKey=%s", LIVE_SHAPED_KEY
        )

        output = stream.getvalue()

    assert LIVE_SHAPED_KEY not in output
    assert REDACTED in output


def test_request_url_logging_is_quieted_at_source() -> None:
    """httpx's INFO request line is the thing that leaked; it stays off."""
    with _configured(LIVE_SHAPED_KEY):
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING


async def test_an_odds_call_publishes_no_key_even_with_httpx_logging_on() -> None:
    """The property, driven through a real provider call.

    httpx is put *back* to INFO first, on purpose. A test that only asserted the logger
    level would pass on the day someone re-enables it or adds a second HTTP client; this
    one fails unless the key is genuinely absent from what was written.
    """
    with _configured(LIVE_SHAPED_KEY) as stream:
        logging.getLogger("httpx").setLevel(logging.INFO)

        provider = OddsApiProvider(
            LIVE_SHAPED_KEY,
            bookmaker="Bet365",
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=[])),
                base_url=DEFAULT_BASE_URL,
            ),
        )
        await provider.fetch_odds([12345])

        output = stream.getvalue()

    # The request line was emitted — otherwise this proves nothing.
    assert "HTTP Request" in output
    assert LIVE_SHAPED_KEY not in output
    assert REDACTED in output

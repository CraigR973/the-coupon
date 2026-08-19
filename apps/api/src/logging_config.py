import logging
import sys
from collections.abc import Sequence

import structlog

#: What a redacted secret renders as. Deliberately visible: a line that *had* a secret in
#: it should look different from one that never did, so the redactor can be seen working.
REDACTED = "<redacted>"

#: Loggers whose INFO output carries request URLs. httpx logs every request line as
#: `HTTP Request: GET <full url> "HTTP/1.1 200 OK"`, and odds-api.io takes its key as a
#: query parameter, so that one line published a live credential on every call. The
#: redactor below is the guarantee; this is just the source, quieted so the log is
#: readable rather than a wall of redactions.
_URL_LOGGING_LIBRARIES = ("httpx", "httpcore")


def _redacting_json_renderer(secrets: Sequence[str]) -> structlog.types.Processor:
    """A JSON renderer that removes known secrets from the finished line.

    Redacting at the *renderer* rather than on the event dict is what makes this a
    property of the log rather than of any one call site. The secret is gone whether it
    arrived in the event message, in a keyword value, nested inside a structure, or from
    a third-party library that knows nothing about this application's conventions — and
    it stays gone if someone later re-enables a quieted logger or adds a second HTTP
    client.
    """
    render_json = structlog.processors.JSONRenderer()

    def render(
        logger: structlog.types.WrappedLogger,
        name: str,
        event_dict: structlog.types.EventDict,
    ) -> str:
        rendered = render_json(logger, name, event_dict)
        if not isinstance(rendered, str):  # pragma: no cover - JSONRenderer returns str
            rendered = str(rendered)
        for secret in secrets:
            rendered = rendered.replace(secret, REDACTED)
        return rendered

    return render


def configure_logging(log_level: str = "INFO", secrets: Sequence[str] = ()) -> None:
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # Render exc_info into a traceback string; without this, log.exception()
            # serializes exc_info as a bare `true` and the traceback is lost.
            structlog.processors.format_exc_info,
            _redacting_json_renderer(tuple(secrets)),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level.upper())

    for name in _URL_LOGGING_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)

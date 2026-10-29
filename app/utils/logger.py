# ialab-standards: logger.py v1.0 - generated, do not edit
# ialab-standards-sha256: beb050c871c51f7a570b355151a7471fe782eea936904e53b23cb74cc6524e5b
"""Standard IALab logging: human-readable console, JSON log file, request correlation.

This module is vendored verbatim into every IALab service. It must stay
dependency-free (standard library only) and free of project-specific values:
everything that varies between projects comes from environment variables, so the
file is byte-identical across repositories and can be checksum-verified.

Environment variables:
    ENV: ``production`` or ``development`` (default). Drives log levels and
        whether the file handler rotates.
    LOG_LEVEL: Explicit level override for the application logger.
    LOG_DIR: Directory holding the log file (default ``logs``).
    LOG_FILE: Log file name inside ``LOG_DIR`` (default ``app.log``).
    LOG_NAMESPACE: Comma-separated logger namespaces configured at the
        application level (default ``app``). The first one is exposed as the
        module-level ``logger``. Loggers outside these namespaces fall back to
        the root level, which is quiet in production.
    IALAB_PROJECT: Project identifier stamped on every JSON record. Must match
        ``project.name`` in the ialab-monitoring project config.

Typical use:
    from app.utils.logger import get_logger

    logger = get_logger(__name__)
    logger.info("Project loaded: %s", project_name)

FastAPI services also install the request middleware so every record emitted
while serving a request carries the same ``request_id``:

    from app.utils.logger import RequestIdMiddleware

    app.add_middleware(RequestIdMiddleware)
"""

import json
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.config import dictConfig
from typing import Any, Awaitable, Callable, Optional

IALAB_LOGGING_VERSION = "1.0"

# Header name carrying a caller-supplied correlation id, and the name used when
# echoing the id back on the response.
REQUEST_ID_HEADER = "x-request-id"

# Bytes and backup count for the rotating file handler used in production.
_MAX_LOG_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 3

# RFC 3339 in UTC with millisecond precision. The OTel Collector json_parser
# reads it back with layout_type gotime and layout 2006-01-02T15:04:05.000Z;
# keep both in sync.
_TS_PRECISION = "milliseconds"

# LogRecord attributes that are part of the standard record and must not be
# copied into the JSON ``attrs`` field.
_RESERVED_RECORD_KEYS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
        "request_id",
    }
)

_ENV = os.getenv("ENV", "development")
_IS_PROD = _ENV == "production"
_PROJECT = os.getenv("IALAB_PROJECT", "unknown")
_NAMESPACES = [n.strip() for n in os.getenv("LOG_NAMESPACE", "app").split(",") if n.strip()]
_LOG_DIR = os.getenv("LOG_DIR", "logs")
_LOG_FILE = os.path.join(_LOG_DIR, os.getenv("LOG_FILE", "app.log"))

_DEFAULT_APP_LEVEL = "INFO" if _IS_PROD else "DEBUG"
_APP_LEVEL = os.getenv("LOG_LEVEL", _DEFAULT_APP_LEVEL).upper()
# Third-party libraries stay quiet: only the application namespaces get the
# verbose level, so a dev run is not drowned in library DEBUG output.
_ROOT_LEVEL = "WARNING" if _IS_PROD else "INFO"

# Correlation id for the request currently being served, if any.
_request_id: ContextVar[Optional[str]] = ContextVar("ialab_request_id", default=None)


def get_request_id() -> Optional[str]:
    """Return the correlation id of the request being served, if any.

    Returns:
        The current request id, or None outside of a request context.
    """
    return _request_id.get()


def set_request_id(request_id: Optional[str]) -> None:
    """Bind a correlation id to the current context.

    Args:
        request_id: Identifier to bind, or None to clear it.
    """
    _request_id.set(request_id)


def new_request_id() -> str:
    """Generate a fresh correlation id.

    Returns:
        A hex UUID4 string.
    """
    return uuid.uuid4().hex


class RequestIdFilter(logging.Filter):  # pylint: disable=too-few-public-methods
    """Attach the current correlation id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Set ``record.request_id`` from the context variable.

        Args:
            record: Record being emitted.

        Returns:
            True, so the record is always kept.
        """
        record.request_id = get_request_id() or "-"
        return True


def _iso_utc(created: float) -> str:
    """Format a record timestamp as RFC 3339 UTC with millisecond precision.

    Args:
        created: Epoch seconds taken from ``LogRecord.created``.

    Returns:
        A timestamp such as ``2026-08-18T13:05:58.123Z``.
    """
    stamp = datetime.fromtimestamp(created, tz=timezone.utc)
    return stamp.isoformat(timespec=_TS_PRECISION).replace("+00:00", "Z")


class JsonFormatter(logging.Formatter):
    """Render a log record as a single-line JSON object.

    The field names are the contract consumed by the OTel Collector and by the
    ialab-monitoring log ingestion, so they must not be renamed lightly.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serialise a record to a JSON string.

        Args:
            record: Record being emitted.

        Returns:
            A single-line JSON document, newline-free.
        """
        payload: dict[str, Any] = {
            "ts": _iso_utc(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "project": _PROJECT,
            "env": _ENV,
            "file": record.filename,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        attrs = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_RECORD_KEYS and not key.startswith("_")
        }
        if attrs:
            payload["attrs"] = _jsonify(attrs)

        return json.dumps(payload, ensure_ascii=False, default=str)


def _jsonify(attrs: dict[str, Any]) -> dict[str, Any]:
    """Coerce arbitrary ``extra`` values into JSON-serialisable ones.

    Args:
        attrs: Raw extra attributes taken from the log record.

    Returns:
        A dict whose values are all JSON-serialisable.
    """
    safe: dict[str, Any] = {}
    for key, value in attrs.items():
        if isinstance(value, (str, int, float, bool, type(None))):
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe


def _file_handler_config() -> dict[str, Any]:
    """Build the file handler config: rotating in production, plain otherwise.

    Returns:
        A logging dictConfig handler definition writing JSON records.
    """
    base: dict[str, Any] = {
        "level": _APP_LEVEL,
        "formatter": "json",
        "filters": ["request_id"],
        "filename": _LOG_FILE,
        "encoding": "utf-8",
    }
    if _IS_PROD:
        base.update(
            {
                "class": "logging.handlers.RotatingFileHandler",
                "maxBytes": _MAX_LOG_BYTES,
                "backupCount": _LOG_BACKUP_COUNT,
            }
        )
    else:
        base.update({"class": "logging.FileHandler", "mode": "a"})
    return base


def _log_config() -> dict[str, Any]:
    """Build the full logging dictConfig for an IALab service.

    Returns:
        A dictConfig mapping wiring the console, file, and stderr handlers.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        # Pass the classes themselves rather than dotted paths: dictConfig runs
        # while this module is still importing, so a dotted path would not yet
        # resolve as an attribute of its parent package.
        "filters": {
            "request_id": {"()": RequestIdFilter},
        },
        "formatters": {
            "console": {
                "format": "[%(levelname)s] %(asctime)s - %(name)s - [%(request_id)s] - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {"()": JsonFormatter},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": _APP_LEVEL,
                "formatter": "console",
                "filters": ["request_id"],
                "stream": "ext://sys.stdout",
            },
            "file": _file_handler_config(),
        },
        "root": {
            "handlers": ["console", "file"],
            "level": _ROOT_LEVEL,
        },
        "loggers": {
            namespace: {
                "handlers": ["console", "file"],
                "level": _APP_LEVEL,
                "propagate": False,
            }
            for namespace in _NAMESPACES
        },
    }


def _init_logging() -> logging.Logger:
    """Configure the logging stack once and return the application logger.

    Returns:
        The logger named after the first ``LOG_NAMESPACE`` entry.
    """
    os.makedirs(_LOG_DIR, exist_ok=True)
    dictConfig(_log_config())
    return logging.getLogger(_NAMESPACES[0])


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger wired to the standard IALab handlers.

    Args:
        name: Logger name, typically ``__name__``. Defaults to the application
            namespace when omitted.

    Returns:
        A configured logger. Module loggers propagate to the root handlers, so
        they inherit the console and JSON file output.
    """
    return logging.getLogger(name) if name else logger


class RequestIdMiddleware:  # pylint: disable=too-few-public-methods
    """Pure-ASGI middleware binding a correlation id to each HTTP request.

    Reuses an inbound ``X-Request-ID`` header when present so a correlation id
    can span several services, generates one otherwise, and echoes it back on
    the response.
    """

    def __init__(self, app: Callable) -> None:
        """Wrap an ASGI application.

        Args:
            app: The downstream ASGI application.
        """
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        """Handle one ASGI event, binding a request id for HTTP scopes.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _inbound_request_id(scope) or new_request_id()
        token = _request_id.set(request_id)
        try:
            await self.app(scope, receive, _send_with_request_id(send, request_id))
        finally:
            _request_id.reset(token)


def _inbound_request_id(scope: dict) -> Optional[str]:
    """Extract a caller-supplied request id from the ASGI scope headers.

    Args:
        scope: ASGI connection scope.

    Returns:
        The inbound request id, or None when the header is absent or empty.
    """
    target = REQUEST_ID_HEADER.encode()
    for key, value in scope.get("headers", []):
        if key.lower() == target:
            decoded = value.decode("latin-1").strip()
            if decoded:
                return decoded[:64]
    return None


def _send_with_request_id(send: Callable, request_id: str) -> Callable[[dict], Awaitable[None]]:
    """Wrap an ASGI ``send`` so the response carries the request id header.

    Args:
        send: Original ASGI send callable.
        request_id: Correlation id to echo back.

    Returns:
        A send callable injecting the header on ``http.response.start``.
    """

    async def wrapped(message: dict) -> None:
        if message["type"] == "http.response.start":
            headers = list(message.get("headers", []))
            headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
            message = {**message, "headers": headers}
        await send(message)

    return wrapped


logger = _init_logging()

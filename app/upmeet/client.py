"""Thin HTTP client for the Upmeet API, authenticated by API key."""

import time
from typing import Any, Optional

import httpx

from app.core.settings import Settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRY_BACKOFF_SECONDS = 1.0


class UpmeetApiError(RuntimeError):
    """Raised when the Upmeet API answers with a non-success status."""


class UpmeetClient:
    """Synchronous Upmeet client sending the API key in ``X-Api-Token``.

    Args:
        settings: Connection settings (API key, base URL, timeout, retries).
        transport: Optional httpx transport, used by tests to mock the API.
    """

    def __init__(self, settings: Settings, transport: Optional[httpx.BaseTransport] = None):
        self._max_retries = max(1, settings.max_retries)
        self._http = httpx.Client(
            base_url=settings.base_url,
            headers={"X-Api-Token": settings.api_key, "Accept": "application/json"},
            timeout=settings.timeout_seconds,
            transport=transport,
        )

    def get_json(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Send a GET request and decode the JSON body, retrying transient failures.

        Args:
            path: API path, e.g. ``/meetings``.
            params: Query parameters; ``None`` values are dropped.

        Returns:
            The decoded JSON body.

        Raises:
            UpmeetApiError: On a non-success status or when retries are exhausted.
        """
        query = {key: value for key, value in (params or {}).items() if value is not None}
        for attempt in range(1, self._max_retries + 1):
            is_last_attempt = attempt == self._max_retries
            try:
                response = self._http.get(path, params=query)
            except httpx.TransportError as exc:
                logger.warning("Upmeet GET %s failed (attempt %s): %s", path, attempt, exc)
                if is_last_attempt:
                    raise UpmeetApiError(f"Upmeet unreachable on GET {path}: {exc}") from exc
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue
            if response.status_code in _RETRYABLE_STATUS_CODES and not is_last_attempt:
                logger.warning("Upmeet GET %s -> %s, retrying", path, response.status_code)
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue
            return _decode_response(path, response)
        raise UpmeetApiError(f"Retries exhausted on GET {path}")


def _decode_response(path: str, response: httpx.Response) -> dict[str, Any]:
    """Turn an HTTP response into JSON, failing loudly on error statuses.

    Args:
        path: Requested path, for error messages.
        response: The HTTP response.

    Returns:
        The decoded JSON body.

    Raises:
        UpmeetApiError: If the status is not 2xx.
    """
    logger.info("Upmeet GET %s -> %s", path, response.status_code)
    if response.status_code in (401, 403):
        raise UpmeetApiError("Upmeet rejected the API key (check UPMEET_API_KEY)")
    if not response.is_success:
        raise UpmeetApiError(f"Upmeet GET {path} failed with status {response.status_code}")
    return response.json()

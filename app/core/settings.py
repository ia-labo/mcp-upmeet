"""Runtime settings read from the environment."""

import os
from dataclasses import dataclass

_DEFAULT_BASE_URL = "https://api.upmeet.ai"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_MAX_RETRIES = 3


@dataclass(frozen=True)
class Settings:
    """Upmeet connection settings.

    Attributes:
        api_key: Upmeet API token, sent in the ``X-Api-Token`` header.
        base_url: Root URL of the Upmeet API.
        timeout_seconds: Timeout applied to every HTTP call.
        max_retries: Attempts on transient failures (network errors, 5xx, 429).
    """

    api_key: str
    base_url: str
    timeout_seconds: float
    max_retries: int


def load_settings() -> Settings:
    """Build the settings from environment variables.

    Returns:
        The loaded settings.

    Raises:
        RuntimeError: If ``UPMEET_API_KEY`` is missing.
    """
    api_key = os.environ.get("UPMEET_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("UPMEET_API_KEY is not set")
    return Settings(
        api_key=api_key,
        base_url=os.environ.get("UPMEET_BASE_URL", _DEFAULT_BASE_URL).rstrip("/"),
        timeout_seconds=float(os.environ.get("UPMEET_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS)),
        max_retries=int(os.environ.get("UPMEET_MAX_RETRIES", _DEFAULT_MAX_RETRIES)),
    )

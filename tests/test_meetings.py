"""Tests for the Upmeet meeting operations against a mocked API."""

import httpx
import pytest

from app.core.settings import Settings
from app.upmeet import UpmeetApiError, UpmeetClient, fetch_meeting_details, list_meetings

_MEETING = {
    "id": 27,
    "name": "Kickoff",
    "status": "finished",
    "createdAt": "2023-04-13T13:13:58+00:00",
    "actuallyStartedAt": "2023-04-13T13:14:22+00:00",
    "endedAt": "2023-04-13T13:18:35+00:00",
    "statistics": {"duration": 2435},
    "tags": [{"name": "daily"}],
    "platform": {"name": "Google Meet"},
    "summary": {"text": "Summary text"},
}


def _build_client(handler) -> UpmeetClient:
    """Build a client whose requests are answered by ``handler``."""
    settings = Settings(
        api_key="TEST_KEY", base_url="https://api.test", timeout_seconds=1, max_retries=1
    )
    return UpmeetClient(settings, transport=httpx.MockTransport(handler))


def _fake_api(request: httpx.Request) -> httpx.Response:
    """Answer like the Upmeet API for the endpoints the server uses."""
    assert request.headers["X-Api-Token"] == "TEST_KEY"
    routes = {
        "/meetings": {"meetings": [_MEETING], "page": 1, "totalPages": 1, "totalResults": 1},
        "/meetings/27": {"meeting": _MEETING},
        "/meetings/27/attendees": {"attendees": [{"id": "a", "name": "A", "emailAddress": None}]},
        "/meetings/27/speakers": {"speakers": [{"id": "s", "name": "Speaker"}]},
        "/meetings/27/full-transcription": {
            "fullTranscription": {"text": "Hello", "duration": "1"}
        },
    }
    return httpx.Response(200, json=routes[request.url.path])


def test_list_meetings_by_theme_sends_tag_filter():
    """The theme is forwarded as ``tagsNames`` and meetings are summarized."""
    seen_params = {}

    def handler(request):
        seen_params.update(request.url.params)
        return _fake_api(request)

    result = list_meetings(_build_client(handler), theme="daily")
    assert seen_params["tagsNames"] == "daily"
    assert "status" not in seen_params
    assert result["meetings"][0]["themes"] == ["daily"]
    assert result["totalResults"] == 1


def test_fetch_meeting_details_merges_endpoints():
    """Details combine meeting, attendees, speakers and transcription."""
    details = fetch_meeting_details(_build_client(_fake_api), 27)
    assert details["durationSeconds"] == 2435
    assert details["summary"] == "Summary text"
    assert details["attendees"][0]["name"] == "A"
    assert details["speakers"][0]["name"] == "Speaker"
    assert details["transcription"] == "Hello"


def test_invalid_api_key_fails_loudly():
    """A 401 raises an explicit error instead of returning empty data."""
    client = _build_client(lambda request: httpx.Response(401))
    with pytest.raises(UpmeetApiError, match="API key"):
        list_meetings(client)

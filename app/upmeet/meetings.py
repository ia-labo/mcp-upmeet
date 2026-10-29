"""Meeting operations. Upmeet "meetings" are what users call projects; tags are themes."""

from typing import Any, Optional

from app.upmeet.client import UpmeetClient


def list_meetings(
    client: UpmeetClient,
    theme: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
) -> dict[str, Any]:
    """List meetings, optionally restricted to a theme (tag name) and a status.

    Args:
        client: Authenticated Upmeet client.
        theme: Tag name to filter on; several can be given comma-separated.
        status: ``pending``, ``in_progress`` or ``finished``.
        page: 1-based page number (50 meetings per page).

    Returns:
        A compact page: meetings (id, name, status, dates, duration, themes) and pagination.
    """
    payload = client.get_json(
        "/meetings",
        params={"tagsNames": theme, "status": status, "page": page, "maxResultsPerPage": 50},
    )
    return {
        "meetings": [_summarize_meeting(meeting) for meeting in payload["meetings"]],
        "page": payload["page"],
        "totalPages": payload["totalPages"],
        "totalResults": payload["totalResults"],
    }


def fetch_meeting_details(
    client: UpmeetClient, meeting_id: int, include_transcription: bool = True
) -> dict[str, Any]:
    """Gather a meeting with its attendees, speakers, summary and transcription.

    Args:
        client: Authenticated Upmeet client.
        meeting_id: Upmeet meeting id.
        include_transcription: Whether to fetch the (potentially long) full transcription.

    Returns:
        The meeting details merged into a single dict.
    """
    meeting = client.get_json(f"/meetings/{meeting_id}")["meeting"]
    details = _summarize_meeting(meeting)
    details["summary"] = (meeting.get("summary") or {}).get("text")
    details["platform"] = (meeting.get("platform") or {}).get("name")
    details["attendees"] = client.get_json(f"/meetings/{meeting_id}/attendees")["attendees"]
    details["speakers"] = client.get_json(f"/meetings/{meeting_id}/speakers").get("speakers", [])
    if include_transcription:
        transcription = client.get_json(
            f"/meetings/{meeting_id}/full-transcription", params={"includeSpeakers": "1"}
        ).get("fullTranscription")
        details["transcription"] = (transcription or {}).get("text")
    return details


def _summarize_meeting(meeting: dict[str, Any]) -> dict[str, Any]:
    """Keep the fields useful to an agent out of a raw meeting payload.

    Args:
        meeting: Raw meeting object from the API.

    Returns:
        The compact representation.
    """
    return {
        "id": meeting["id"],
        "name": meeting.get("name"),
        "status": meeting.get("status"),
        "createdAt": meeting.get("createdAt"),
        "startedAt": meeting.get("actuallyStartedAt"),
        "endedAt": meeting.get("endedAt"),
        "durationSeconds": (meeting.get("statistics") or {}).get("duration"),
        "themes": [tag["name"] for tag in meeting.get("tags") or []],
    }

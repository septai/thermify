from __future__ import annotations

from datetime import UTC, datetime


def _parse_iso8601_utc(timestamp: str) -> datetime:
    """Parse an ISO 8601 string with a Z suffix into a UTC datetime."""
    normalized = timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_utc_iso8601(timestamp: datetime) -> str:
    """Format a datetime as ISO 8601 with milliseconds and a Z suffix."""
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    else:
        timestamp = timestamp.astimezone(UTC)
    return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")

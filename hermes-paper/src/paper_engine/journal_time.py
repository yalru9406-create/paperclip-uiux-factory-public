from __future__ import annotations

from datetime import UTC, datetime

from paper_engine.journal_types import EventId, JournalTimestampError


def parse_utc_timestamp(event_id: EventId, value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JournalTimestampError(event_id, f"invalid UTC timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        raise JournalTimestampError(event_id, f"timestamp {value!r} must include UTC offset")
    return parsed.astimezone(UTC)


def format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")

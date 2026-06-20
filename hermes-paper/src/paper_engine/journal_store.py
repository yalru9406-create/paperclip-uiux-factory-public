from __future__ import annotations

from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from paper_engine.journal_payloads import memory_fact_from_event, memory_retraction_from_event, payload_to_json
from paper_engine.journal_sqlite import (
    connect_journal,
    ensure_schema,
    existing_signature,
    insert_event,
    inspect_journal,
    latest_created_at,
    read_events,
)
from paper_engine.journal_time import format_utc_timestamp, parse_utc_timestamp
from paper_engine.journal_types import (
    AppendBatchResult,
    DuplicateEventMismatchError,
    EventId,
    FactId,
    JournalEvent,
    JournalEventInput,
    JournalInspection,
    JournalStream,
    JournalTimestampError,
    MemoryFact,
    MemoryProjection,
    PreparedEvent,
)


@dataclass(frozen=True, slots=True)
class JournalStore:
    db_path: Path

    def append_batch(self, events: Sequence[JournalEventInput]) -> AppendBatchResult:
        with closing(connect_journal(self.db_path)) as conn:
            ensure_schema(conn)
            inserted = 0
            idempotent = 0
            with conn:
                _ = conn.execute("BEGIN IMMEDIATE")
                last_created_at = latest_created_at(conn)
                for event in events:
                    payload_json = payload_to_json(event)
                    existing = existing_signature(conn, event.typed_event_id)
                    if existing is not None:
                        duplicate_created_at = self._duplicate_created_at_for(event, existing.created_at_utc)
                        if not existing.matches(event, duplicate_created_at, payload_json):
                            raise DuplicateEventMismatchError(event.typed_event_id)
                        idempotent += 1
                        continue
                    created_at_utc = self._created_at_for(event, last_created_at)
                    insert_event(conn, PreparedEvent(event, created_at_utc, payload_json))
                    last_created_at = parse_utc_timestamp(event.typed_event_id, created_at_utc)
                    inserted += 1
        return AppendBatchResult(inserted=inserted, idempotent=idempotent)

    def replay(self) -> tuple[JournalEvent, ...]:
        with closing(connect_journal(self.db_path)) as conn:
            ensure_schema(conn)
            return read_events(conn)

    def rebuild_memory_projection(self, as_of_utc: str | None = None) -> MemoryProjection:
        as_of = (
            datetime.max.replace(tzinfo=UTC)
            if as_of_utc is None
            else parse_utc_timestamp(EventId("as_of"), as_of_utc)
        )
        facts: dict[FactId, MemoryFact] = {}
        for event in self.replay():
            if event.stream is JournalStream.MEMORY_FACT:
                fact = memory_fact_from_event(event)
                expires_at = parse_utc_timestamp(event.event_id, fact.expires_at_utc)
                if expires_at > as_of:
                    facts[fact.fact_id] = fact
                else:
                    _ = facts.pop(fact.fact_id, None)
                continue
            if event.stream is JournalStream.MEMORY_RETRACTION:
                retraction = memory_retraction_from_event(event)
                _ = facts.pop(retraction.typed_fact_id, None)
        return MemoryProjection(active_facts=tuple(facts[key] for key in sorted(facts)))

    def inspect(self) -> JournalInspection:
        with closing(connect_journal(self.db_path)) as conn:
            ensure_schema(conn)
            return inspect_journal(conn, self.db_path)

    def _created_at_for(self, event: JournalEventInput, last_created_at: datetime | None) -> str:
        if event.created_at_utc is None:
            created_at = datetime.now(UTC)
            if last_created_at is not None and created_at <= last_created_at:
                created_at = last_created_at + timedelta(microseconds=1)
            return format_utc_timestamp(created_at)
        created_at = parse_utc_timestamp(event.typed_event_id, event.created_at_utc)
        if last_created_at is not None and created_at <= last_created_at:
            raise JournalTimestampError(event.typed_event_id, "created_at_utc must increase monotonically")
        return format_utc_timestamp(created_at)

    def _duplicate_created_at_for(self, event: JournalEventInput, stored_created_at_utc: str) -> str:
        if event.created_at_utc is None:
            return stored_created_at_utc
        return format_utc_timestamp(parse_utc_timestamp(event.typed_event_id, event.created_at_utc))

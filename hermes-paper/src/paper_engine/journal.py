from __future__ import annotations

from paper_engine.journal_cli import app, inspect_journal, main
from paper_engine.journal_store import JournalStore
from paper_engine.journal_types import (
    SCHEMA_VERSION,
    AppendBatchResult,
    DuplicateEventMismatchError,
    EventId,
    FactId,
    JournalError,
    JournalEvent,
    JournalEventInput,
    JournalInspection,
    JournalPayloadError,
    JournalSchemaMismatchError,
    JournalStream,
    JournalTimestampError,
    MemoryFact,
    MemoryFactPayload,
    MemoryProjection,
    MemoryRetractionPayload,
)

__all__ = [
    "SCHEMA_VERSION",
    "AppendBatchResult",
    "DuplicateEventMismatchError",
    "EventId",
    "FactId",
    "JournalError",
    "JournalEvent",
    "JournalEventInput",
    "JournalInspection",
    "JournalPayloadError",
    "JournalSchemaMismatchError",
    "JournalStore",
    "JournalStream",
    "JournalTimestampError",
    "MemoryFact",
    "MemoryFactPayload",
    "MemoryProjection",
    "MemoryRetractionPayload",
    "app",
    "inspect_journal",
    "main",
]


if __name__ == "__main__":
    app()

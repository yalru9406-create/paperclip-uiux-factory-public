from __future__ import annotations

import sqlite3
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, Protocol

from paper_engine.journal_payloads import payload_from_json
from paper_engine.journal_time import parse_utc_timestamp
from paper_engine.journal_types import (
    SCHEMA_VERSION,
    DatabaseScalar,
    EventId,
    ExistingEventSignature,
    JournalEvent,
    JournalInspection,
    JournalPayloadError,
    JournalSchemaMismatchError,
    JournalStream,
    PreparedEvent,
)

SQLITE_LOCK_RETRY_ATTEMPTS: Final = 20
SQLITE_LOCK_RETRY_DELAY_SECONDS: Final = 0.05


class SqliteRow(Protocol):
    def __getitem__(self, key: str | int) -> DatabaseScalar: ...


class SqliteCursor(Protocol):
    def fetchone(self) -> SqliteRow | None: ...

    def fetchall(self) -> Sequence[SqliteRow]: ...


def connect_journal(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    _ = conn.execute("PRAGMA busy_timeout = 30000")
    _ = conn.execute("PRAGMA foreign_keys = ON")
    for attempt in range(SQLITE_LOCK_RETRY_ATTEMPTS):
        try:
            _ = conn.execute("PRAGMA journal_mode = WAL")
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == SQLITE_LOCK_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(SQLITE_LOCK_RETRY_DELAY_SECONDS)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    _ = conn.execute("CREATE TABLE IF NOT EXISTS journal_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    _ = conn.execute(
        " ".join(
            (
                "CREATE TABLE IF NOT EXISTS events",
                "(sequence INTEGER PRIMARY KEY AUTOINCREMENT,",
                "event_id TEXT NOT NULL UNIQUE,",
                "stream TEXT NOT NULL, subject TEXT,",
                "created_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL)",
            )
        )
    )
    _ = conn.execute("CREATE INDEX IF NOT EXISTS idx_events_stream_sequence ON events(stream, sequence)")
    _ensure_append_only_triggers(conn)
    current = metadata_schema_version(conn)
    if current is None:
        _ = conn.execute(
            "INSERT INTO journal_metadata(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        _ = conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        return
    if current != SCHEMA_VERSION:
        raise JournalSchemaMismatchError(expected=SCHEMA_VERSION, actual=current)


def metadata_schema_version(conn: sqlite3.Connection) -> int | None:
    row = _fetchone_row(conn.execute("SELECT value FROM journal_metadata WHERE key = 'schema_version'"))
    if row is None:
        return None
    return int(_row_text(row, "value"))


def schema_version(conn: sqlite3.Connection) -> int:
    version = metadata_schema_version(conn)
    if version is None:
        raise JournalSchemaMismatchError(expected=SCHEMA_VERSION, actual=0)
    return version


def latest_created_at(conn: sqlite3.Connection) -> datetime | None:
    row = _fetchone_row(conn.execute("SELECT created_at_utc FROM events ORDER BY sequence DESC LIMIT 1"))
    if row is None:
        return None
    return parse_utc_timestamp(EventId("latest"), _row_text(row, "created_at_utc"))


def existing_signature(conn: sqlite3.Connection, event_id: EventId) -> ExistingEventSignature | None:
    row = _fetchone_row(
        conn.execute(
            "SELECT stream, subject, created_at_utc, payload_json FROM events WHERE event_id = ?",
            (str(event_id),),
        )
    )
    if row is None:
        return None
    return ExistingEventSignature(
        stream=stream_from_db(_row_text(row, "stream")),
        subject=_row_nullable_text(row, "subject"),
        created_at_utc=_row_text(row, "created_at_utc"),
        payload_json=_row_text(row, "payload_json"),
    )


def insert_event(conn: sqlite3.Connection, prepared: PreparedEvent) -> None:
    _ = conn.execute(
        "INSERT INTO events(event_id, stream, subject, created_at_utc, payload_json) VALUES (?, ?, ?, ?, ?)",
        (
            prepared.event.event_id,
            prepared.event.stream.value,
            prepared.event.subject,
            prepared.created_at_utc,
            prepared.payload_json,
        ),
    )


def read_events(conn: sqlite3.Connection) -> tuple[JournalEvent, ...]:
    rows = _fetchall_rows(
        conn.execute(
            " ".join(
                (
                    "SELECT sequence, event_id, stream, subject, created_at_utc, payload_json",
                    "FROM events ORDER BY sequence ASC",
                )
            )
        )
    )
    return tuple(_row_to_event(row) for row in rows)


def inspect_journal(conn: sqlite3.Connection, db_path: Path) -> JournalInspection:
    version = schema_version(conn)
    journal_mode = _first_text(conn, "PRAGMA journal_mode").lower()
    event_count = _first_int(conn, "SELECT COUNT(*) FROM events")
    stream_counts = {stream: 0 for stream in JournalStream}
    rows = _fetchall_rows(conn.execute("SELECT stream, COUNT(*) AS count FROM events GROUP BY stream"))
    for row in rows:
        stream_counts[stream_from_db(_row_text(row, "stream"))] = _row_int(row, "count")
    return JournalInspection(db_path, version, journal_mode, event_count, stream_counts)


def stream_from_db(value: str) -> JournalStream:
    try:
        return JournalStream(value)
    except ValueError as exc:
        raise JournalPayloadError(EventId("db"), f"unknown stored stream {value!r}") from exc


def _ensure_append_only_triggers(conn: sqlite3.Connection) -> None:
    _ = conn.execute(
        " ".join(
            (
                "CREATE TRIGGER IF NOT EXISTS events_append_only_update",
                "BEFORE UPDATE ON events BEGIN",
                "SELECT RAISE(ABORT, 'events table is append-only');",
                "END",
            )
        )
    )
    _ = conn.execute(
        " ".join(
            (
                "CREATE TRIGGER IF NOT EXISTS events_append_only_delete",
                "BEFORE DELETE ON events BEGIN",
                "SELECT RAISE(ABORT, 'events table is append-only');",
                "END",
            )
        )
    )


def _row_to_event(row: SqliteRow) -> JournalEvent:
    return JournalEvent(
        sequence=_row_int(row, "sequence"),
        event_id=EventId(_row_text(row, "event_id")),
        stream=stream_from_db(_row_text(row, "stream")),
        subject=_row_nullable_text(row, "subject"),
        created_at_utc=_row_text(row, "created_at_utc"),
        payload=payload_from_json(_row_text(row, "payload_json")),
    )


def _fetchone_row(cursor: SqliteCursor) -> SqliteRow | None:
    return cursor.fetchone()


def _fetchall_rows(cursor: SqliteCursor) -> tuple[SqliteRow, ...]:
    return tuple(cursor.fetchall())


def _first_text(conn: sqlite3.Connection, sql: str) -> str:
    row = _fetchone_row(conn.execute(sql))
    if row is None:
        raise JournalSchemaMismatchError(expected=SCHEMA_VERSION, actual=0)
    value = _row_scalar(row, 0)
    return str(value)


def _first_int(conn: sqlite3.Connection, sql: str) -> int:
    row = _fetchone_row(conn.execute(sql))
    if row is None:
        raise JournalSchemaMismatchError(expected=SCHEMA_VERSION, actual=0)
    value = _row_scalar(row, 0)
    if value is None:
        raise JournalSchemaMismatchError(expected=SCHEMA_VERSION, actual=0)
    return int(value)


def _row_text(row: SqliteRow, key: str) -> str:
    value = _row_scalar(row, key)
    if isinstance(value, str):
        return value
    return str(value)


def _row_nullable_text(row: SqliteRow, key: str) -> str | None:
    value = _row_scalar(row, key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _row_int(row: SqliteRow, key: str) -> int:
    value = _row_scalar(row, key)
    if value is None:
        raise JournalPayloadError(EventId("db"), f"stored integer column {key!r} is NULL")
    return int(value)


def _row_scalar(row: SqliteRow, key: str | int) -> DatabaseScalar:
    return row[key]

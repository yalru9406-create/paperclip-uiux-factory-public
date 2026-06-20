from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from paper_engine.journal import (
    DuplicateEventMismatchError,
    JournalEventInput,
    JournalPayloadError,
    JournalStore,
    JournalStream,
)


def test_append_replay_retract_memory_fact(tmp_path: Path) -> None:
    # Given: a paper journal with one durable memory fact.
    store = JournalStore(tmp_path / "paper_journal.sqlite3")
    fact = JournalEventInput(
        event_id="evt-memory-1",
        stream=JournalStream.MEMORY_FACT,
        subject="BTCUSDT",
        created_at_utc="2026-01-01T00:00:00Z",
        payload={
            "fact_id": "fact-btc-regime",
            "text": "BTC volatility expansion favours smaller paper position sizing.",
            "confidence": 0.82,
            "expires_at_utc": "2026-01-08T00:00:00Z",
        },
    )

    # When: the fact is appended twice and then retracted.
    first = store.append_batch((fact,))
    second = store.append_batch((fact,))
    before_retraction = store.rebuild_memory_projection(as_of_utc="2026-01-02T00:00:00Z")
    _ = store.append_batch(
        (
            JournalEventInput(
                event_id="evt-retract-1",
                stream=JournalStream.MEMORY_RETRACTION,
                subject="BTCUSDT",
                created_at_utc="2026-01-03T00:00:00Z",
                payload={"fact_id": "fact-btc-regime", "reason": "superseded_by_new_validation"},
            ),
        )
    )
    after_retraction = store.rebuild_memory_projection(as_of_utc="2026-01-04T00:00:00Z")
    replay = store.replay()
    inspection = store.inspect()

    # Then: duplicate identical append is idempotent and replay/rebuild is deterministic.
    assert first.inserted == 1
    assert second.inserted == 0
    assert tuple(fact.fact_id for fact in before_retraction.active_facts) == ("fact-btc-regime",)
    assert after_retraction.active_facts == ()
    assert tuple(event.event_id for event in replay) == ("evt-memory-1", "evt-retract-1")
    assert store.rebuild_memory_projection(as_of_utc="2026-01-04T00:00:00Z") == after_retraction
    assert inspection.schema_version == 1
    assert inspection.journal_mode == "wal"
    assert inspection.event_count == 2
    assert inspection.stream_counts[JournalStream.MEMORY_FACT] == 1
    assert inspection.stream_counts[JournalStream.MEMORY_RETRACTION] == 1


def test_duplicate_event_id_semantic_mismatch_rejected(tmp_path: Path) -> None:
    # Given: a journal already containing an event id.
    store = JournalStore(tmp_path / "paper_journal.sqlite3")
    _ = store.append_batch(
        (
            JournalEventInput(
                event_id="evt-policy-1",
                stream=JournalStream.POLICY_DECISION,
                created_at_utc="2026-01-01T00:00:00Z",
                payload={"verdict": "NO_ACTION", "policy_version": "paper-v1"},
            ),
        )
    )

    # When: the same event id is reused with a different semantic payload.
    with pytest.raises(DuplicateEventMismatchError):
        _ = store.append_batch(
            (
                JournalEventInput(
                    event_id="evt-policy-1",
                    stream=JournalStream.POLICY_DECISION,
                    created_at_utc="2026-01-01T00:00:01Z",
                    payload={"verdict": "PROPOSE_REDUCE", "policy_version": "paper-v1"},
                ),
            )
        )

    # Then: the failed duplicate append does not mutate the event log.
    replay = store.replay()
    assert len(replay) == 1
    assert replay[0].payload["verdict"] == "NO_ACTION"


def test_duplicate_event_id_timestamp_mismatch_rejected(tmp_path: Path) -> None:
    # Given: a journal already containing a policy event.
    store = JournalStore(tmp_path / "paper_journal.sqlite3")
    original = JournalEventInput(
        event_id="evt-policy-timestamp",
        stream=JournalStream.POLICY_DECISION,
        subject="BTCUSDT",
        created_at_utc="2026-01-01T00:00:00Z",
        payload={"verdict": "NO_ACTION", "policy_version": "paper-v1"},
    )
    _ = store.append_batch((original,))

    # When: the same event id, stream, subject, and payload are reused with a different timestamp.
    with pytest.raises(DuplicateEventMismatchError):
        _ = store.append_batch(
            (
                JournalEventInput(
                    event_id=original.event_id,
                    stream=original.stream,
                    subject=original.subject,
                    created_at_utc="2026-01-01T00:00:01Z",
                    payload=original.payload,
                ),
            )
        )

    # Then: the timestamp mismatch is not idempotent and the stored event is unchanged.
    replay = store.replay()
    assert len(replay) == 1
    assert replay[0].event_id == original.typed_event_id
    assert replay[0].created_at_utc == "2026-01-01T00:00:00.000000Z"
    assert replay[0].payload == original.payload


def test_invalid_stream_and_memory_payload_are_rejected(tmp_path: Path) -> None:
    # Given: a journal boundary that only accepts known streams and governed memory facts.
    store = JournalStore(tmp_path / "paper_journal.sqlite3")

    # When / Then: an unknown stream cannot become a journal event.
    with pytest.raises(ValidationError):
        _ = JournalEventInput.model_validate(
            {
                "event_id": "evt-private-chat",
                "stream": "private_chat",
                "payload": {"text": "raw private material"},
            }
        )

    # When / Then: memory facts must carry confidence and expiry.
    with pytest.raises(JournalPayloadError):
        _ = store.append_batch(
            (
                JournalEventInput(
                    event_id="evt-memory-invalid",
                    stream=JournalStream.MEMORY_FACT,
                    created_at_utc="2026-01-01T00:00:00Z",
                    payload={"fact_id": "fact-missing-governance", "text": "missing expiry and confidence"},
                ),
            )
        )


@pytest.mark.parametrize(
    "sensitive_key",
    (
        "api_key",
        "APIKEY",
        "secret",
        "token",
        "password",
        "cookie",
        "authorization",
        "auth_header",
        "private_key",
    ),
)
def test_nested_sensitive_payload_keys_are_rejected(tmp_path: Path, sensitive_key: str) -> None:
    # Given: a journal event with a forbidden key hidden inside nested JSON.
    store = JournalStore(tmp_path / "paper_journal.sqlite3")
    event = JournalEventInput(
        event_id=f"evt-sensitive-{sensitive_key.lower()}",
        stream=JournalStream.MARKET_DATA,
        created_at_utc="2026-01-01T00:00:00Z",
        payload={"symbol": "BTCUSDT", "outer": [{"inner": {sensitive_key: "SHOULD_NOT_STORE"}}]},
    )

    # When / Then: the append boundary rejects the event before persistence.
    with pytest.raises(JournalPayloadError):
        _ = store.append_batch((event,))


def test_events_table_rejects_direct_update_and_delete(tmp_path: Path) -> None:
    # Given: a journal whose schema has been initialized with one event.
    db_path = tmp_path / "paper_journal.sqlite3"
    store = JournalStore(db_path)
    _ = store.append_batch(
        (
            JournalEventInput(
                event_id="evt-policy-direct-sql",
                stream=JournalStream.POLICY_DECISION,
                created_at_utc="2026-01-01T00:00:00Z",
                payload={"verdict": "NO_ACTION"},
            ),
        )
    )

    # When / Then: direct SQL attempts to rewrite or remove events abort at the DB layer.
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            _ = conn.execute("UPDATE events SET payload_json = '{}' WHERE event_id = 'evt-policy-direct-sql'")
        with pytest.raises(sqlite3.IntegrityError):
            _ = conn.execute("DELETE FROM events WHERE event_id = 'evt-policy-direct-sql'")

    replay = store.replay()
    assert len(replay) == 1
    assert replay[0].payload == {"verdict": "NO_ACTION"}


def test_concurrent_append_batches_are_serialized(tmp_path: Path) -> None:
    # Given: several journal writers sharing one SQLite database.
    db_path = tmp_path / "paper_journal.sqlite3"

    def append_one(index: int) -> int:
        writer = JournalStore(db_path)
        result = writer.append_batch(
            (
                JournalEventInput(
                    event_id=f"evt-market-{index}",
                    stream=JournalStream.MARKET_DATA,
                    payload={"symbol": "BTCUSDT", "sequence": index},
                ),
            )
        )
        return result.inserted

    # When: independent writers append through transactions.
    with ThreadPoolExecutor(max_workers=4) as executor:
        inserted = tuple(executor.map(append_one, range(10)))

    # Then: every event is present exactly once in deterministic replay order.
    store = JournalStore(db_path)
    assert inserted == (1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
    replay = store.replay()
    assert sorted(event.event_id for event in replay) == [f"evt-market-{index}" for index in range(10)]
    assert tuple(event.created_at_utc for event in replay) == tuple(sorted(event.created_at_utc for event in replay))

from __future__ import annotations

import json
from typing import Final

from pydantic import JsonValue, TypeAdapter, ValidationError

from paper_engine.journal_time import format_utc_timestamp, parse_utc_timestamp
from paper_engine.journal_types import (
    JournalEvent,
    JournalEventInput,
    JournalPayloadError,
    JournalStream,
    JsonPayload,
    MemoryFact,
    MemoryFactPayload,
    MemoryRetractionPayload,
)

_PAYLOAD_ADAPTER: Final = TypeAdapter(JsonPayload)
_JSON_LIST_ADAPTER: Final = TypeAdapter(list[JsonValue])
_FORBIDDEN_PAYLOAD_KEYS: Final = frozenset(
    {
        "account_id",
        "api_key",
        "apikey",
        "api_secret",
        "auth_header",
        "authorization",
        "cookie",
        "cookies",
        "password",
        "private_chat",
        "private_key",
        "raw_exchange_payload",
        "raw_private_chat",
        "secret",
        "token",
    }
)


def payload_to_json(event: JournalEventInput) -> str:
    forbidden_key = find_forbidden_payload_key(event.payload)
    if forbidden_key is not None:
        raise JournalPayloadError(event.typed_event_id, f"forbidden key {forbidden_key!r}")
    validate_event_payload(event)
    try:
        return json.dumps(event.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except ValueError as exc:
        raise JournalPayloadError(event.typed_event_id, str(exc)) from exc


def payload_from_json(value: str) -> JsonPayload:
    return _PAYLOAD_ADAPTER.validate_json(value)


def find_forbidden_payload_key(payload: JsonPayload) -> str | None:
    for key, nested in payload.items():
        normalized = key.strip().lower()
        if normalized in _FORBIDDEN_PAYLOAD_KEYS:
            return key
        nested_key = _find_forbidden_json_value(nested)
        if nested_key is not None:
            return nested_key
    return None


def validate_event_payload(event: JournalEventInput) -> None:
    if event.stream is JournalStream.MEMORY_FACT:
        try:
            fact = MemoryFactPayload.model_validate(event.payload)
        except ValidationError as exc:
            raise JournalPayloadError(event.typed_event_id, str(exc)) from exc
        _ = parse_utc_timestamp(event.typed_event_id, fact.expires_at_utc)
        return
    if event.stream is JournalStream.MEMORY_RETRACTION:
        try:
            _ = MemoryRetractionPayload.model_validate(event.payload)
        except ValidationError as exc:
            raise JournalPayloadError(event.typed_event_id, str(exc)) from exc


def memory_fact_from_event(event: JournalEvent) -> MemoryFact:
    try:
        payload = MemoryFactPayload.model_validate(event.payload)
    except ValidationError as exc:
        raise JournalPayloadError(event.event_id, str(exc)) from exc
    return MemoryFact(
        fact_id=payload.typed_fact_id,
        subject=event.subject,
        text=payload.text,
        confidence=payload.confidence,
        expires_at_utc=format_utc_timestamp(parse_utc_timestamp(event.event_id, payload.expires_at_utc)),
        source_event_id=event.event_id,
        created_at_utc=event.created_at_utc,
    )


def memory_retraction_from_event(event: JournalEvent) -> MemoryRetractionPayload:
    try:
        return MemoryRetractionPayload.model_validate(event.payload)
    except ValidationError as exc:
        raise JournalPayloadError(event.event_id, str(exc)) from exc


def _find_forbidden_json_value(value: JsonValue) -> str | None:
    if isinstance(value, dict):
        return find_forbidden_payload_key(_PAYLOAD_ADAPTER.validate_python(value))
    if isinstance(value, list):
        for nested in _JSON_LIST_ADAPTER.validate_python(value):
            nested_key = _find_forbidden_json_value(nested)
            if nested_key is not None:
                return nested_key
    return None

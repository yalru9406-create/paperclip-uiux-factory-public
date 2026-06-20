from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import ClassVar, Final, NewType, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from typing_extensions import override

SCHEMA_VERSION: Final = 1
EventId = NewType("EventId", str)
FactId = NewType("FactId", str)
JsonPayload: TypeAlias = dict[str, JsonValue]
DatabaseScalar: TypeAlias = str | int | float | bytes | None


@unique
class JournalStream(StrEnum):
    MARKET_DATA = "market_data"
    REGIME = "regime"
    STRATEGY_INTENT = "strategy_intent"
    POLICY_DECISION = "policy_decision"
    APPROVAL = "approval"
    ORDER_COMMAND = "order_command"
    ORDER_ACK = "order_ack"
    ORDER_FILL = "order_fill"
    RISK_EVENT = "risk_event"
    MEMORY_FACT = "memory_fact"
    MEMORY_RETRACTION = "memory_retraction"


class JournalError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class JournalSchemaMismatchError(JournalError):
    expected: int
    actual: int

    @override
    def __str__(self) -> str:
        return f"journal schema_version {self.actual} != expected {self.expected}"


@dataclass(frozen=True, slots=True)
class DuplicateEventMismatchError(JournalError):
    event_id: EventId

    @override
    def __str__(self) -> str:
        return f"duplicate event_id {self.event_id} has a semantic mismatch"


@dataclass(frozen=True, slots=True)
class JournalPayloadError(JournalError):
    event_id: EventId
    reason: str

    @override
    def __str__(self) -> str:
        return f"journal event {self.event_id} payload rejected: {self.reason}"


@dataclass(frozen=True, slots=True)
class JournalTimestampError(JournalError):
    event_id: EventId
    reason: str

    @override
    def __str__(self) -> str:
        return f"journal event {self.event_id} timestamp rejected: {self.reason}"


class JournalEventInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    event_id: str = Field(min_length=1)
    stream: JournalStream
    subject: str | None = Field(default=None, min_length=1)
    created_at_utc: str | None = Field(default=None, min_length=1)
    payload: JsonPayload = Field(default_factory=dict)

    @property
    def typed_event_id(self) -> EventId:
        return EventId(self.event_id)


class MemoryFactPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    fact_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    expires_at_utc: str = Field(min_length=1)

    @property
    def typed_fact_id(self) -> FactId:
        return FactId(self.fact_id)


class MemoryRetractionPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    fact_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    @property
    def typed_fact_id(self) -> FactId:
        return FactId(self.fact_id)


@dataclass(frozen=True, slots=True)
class AppendBatchResult:
    inserted: int
    idempotent: int


@dataclass(frozen=True, slots=True)
class JournalEvent:
    sequence: int
    event_id: EventId
    stream: JournalStream
    subject: str | None
    created_at_utc: str
    payload: JsonPayload


@dataclass(frozen=True, slots=True)
class MemoryFact:
    fact_id: FactId
    subject: str | None
    text: str
    confidence: float
    expires_at_utc: str
    source_event_id: EventId
    created_at_utc: str


@dataclass(frozen=True, slots=True)
class MemoryProjection:
    active_facts: tuple[MemoryFact, ...]


@dataclass(frozen=True, slots=True)
class JournalInspection:
    db_path: Path
    schema_version: int
    journal_mode: str
    event_count: int
    stream_counts: dict[JournalStream, int]


@dataclass(frozen=True, slots=True)
class ExistingEventSignature:
    stream: JournalStream
    subject: str | None
    created_at_utc: str
    payload_json: str

    def matches(self, event: JournalEventInput, created_at_utc: str, payload_json: str) -> bool:
        return (
            self.stream is event.stream
            and self.subject == event.subject
            and self.created_at_utc == created_at_utc
            and self.payload_json == payload_json
        )


@dataclass(frozen=True, slots=True)
class PreparedEvent:
    event: JournalEventInput
    created_at_utc: str
    payload_json: str

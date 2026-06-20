from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from paper_engine.models import ENGINE_NAME, NewsEvent


class NewsEventPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    symbol: str = "GLOBAL"
    event_time_ms: int | None = None
    sentiment_score: float
    severity_score: float
    source: str
    headline: str

    def to_event(self, default_time_ms: int) -> NewsEvent:
        return NewsEvent(
            engine=ENGINE_NAME,
            symbol=self.symbol.upper(),
            event_time_ms=self.event_time_ms if self.event_time_ms is not None else default_time_ms,
            sentiment_score=self.sentiment_score,
            severity_score=self.severity_score,
            source=self.source,
            headline=self.headline,
        )


def parse_news_event_json(raw: str, default_time_ms: int) -> NewsEvent:
    return NewsEventPayload.model_validate_json(raw).to_event(default_time_ms)

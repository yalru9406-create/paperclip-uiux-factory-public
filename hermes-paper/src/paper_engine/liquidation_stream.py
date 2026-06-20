from __future__ import annotations

from typing import Final

import anyio
from pydantic import TypeAdapter, ValidationError
from websockets.asyncio.client import connect

from paper_engine.api_models import ForceOrderPayload
from paper_engine.models import ENGINE_NAME, LiquidationEvent, MarketSide

FORCE_ORDER_STREAM_URL: Final = "wss://fstream.binance.com/ws/!forceOrder@arr"


async def collect_liquidations(sample_seconds: float) -> list[LiquidationEvent]:
    events: list[LiquidationEvent] = []
    with anyio.move_on_after(sample_seconds):
        async with connect(FORCE_ORDER_STREAM_URL, open_timeout=5.0, ping_interval=20.0) as websocket:
            while True:
                raw = await websocket.recv()
                events.extend(parse_force_orders(raw))
    return events


def parse_force_orders(raw: str | bytes) -> list[LiquidationEvent]:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    batch_adapter = TypeAdapter(list[ForceOrderPayload])
    single_adapter = TypeAdapter(ForceOrderPayload)
    try:
        payloads = batch_adapter.validate_json(text)
    except ValidationError:
        try:
            payloads = [single_adapter.validate_json(text)]
        except ValidationError:
            return []
    return [event_from_payload(payload) for payload in payloads]


def event_from_payload(payload: ForceOrderPayload) -> LiquidationEvent:
    side = MarketSide(payload.order.side)
    return LiquidationEvent(
        engine=ENGINE_NAME,
        symbol=payload.order.symbol,
        event_time_ms=payload.event_time_ms,
        side=side,
        quote_volume=payload.order.average_price * payload.order.original_quantity,
    )

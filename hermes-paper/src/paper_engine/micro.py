from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from paper_engine.api_models import AggTradePayload, DepthPayload, FundingPayload, OpenInterestPayload
from paper_engine.models import ENGINE_NAME, LiquidationEvent, MarketSide, MicrostructureSnapshot


@dataclass(frozen=True, slots=True)
class MicroCollectConfig:
    depth_limit: int = 20
    agg_trade_limit: int = 100
    sample_seconds: float = 2.0


@dataclass(frozen=True, slots=True)
class MicroSnapshotInput:
    symbol: str
    depth: DepthPayload
    trades: list[AggTradePayload]
    liquidation_events: list[LiquidationEvent]
    open_interest: OpenInterestPayload
    funding: FundingPayload


class MicroGateway(Protocol):
    async def depth(self, symbol: str, limit: int) -> DepthPayload: ...

    async def agg_trades(self, symbol: str, limit: int) -> list[AggTradePayload]: ...

    async def open_interest(self, symbol: str) -> OpenInterestPayload: ...

    async def funding(self, symbol: str) -> FundingPayload: ...


async def micro_snapshot(
    gateway: MicroGateway,
    symbol: str,
    liquidation_events: list[LiquidationEvent],
    config: MicroCollectConfig,
) -> MicrostructureSnapshot:
    depth = await gateway.depth(symbol, config.depth_limit)
    trades = await gateway.agg_trades(symbol, config.agg_trade_limit)
    oi = await gateway.open_interest(symbol)
    funding = await gateway.funding(symbol)
    return build_micro_snapshot(MicroSnapshotInput(symbol, depth, trades, liquidation_events, oi, funding))


def build_micro_snapshot(snapshot_input: MicroSnapshotInput) -> MicrostructureSnapshot:
    symbol = snapshot_input.symbol
    depth = snapshot_input.depth
    trades = snapshot_input.trades
    liquidation_events = snapshot_input.liquidation_events
    oi = snapshot_input.open_interest
    funding = snapshot_input.funding
    bid_depth = depth_quote(depth.bids)
    ask_depth = depth_quote(depth.asks)
    spread = spread_bps(depth)
    book_imb = ratio_diff(bid_depth, ask_depth)
    buy_quote = sum(trade.quote_volume for trade in trades if not trade.buyer_is_maker)
    sell_quote = sum(trade.quote_volume for trade in trades if trade.buyer_is_maker)
    trade_quote = buy_quote + sell_quote
    sell_ratio = sell_quote / trade_quote if trade_quote > 0 else 0.0
    symbol_liqs = [event for event in liquidation_events if event.symbol == symbol]
    liq_buy = sum(event.quote_volume for event in symbol_liqs if event.side is MarketSide.BUY)
    liq_sell = sum(event.quote_volume for event in symbol_liqs if event.side is MarketSide.SELL)
    liq_imb = ratio_diff(liq_sell, liq_buy)
    score = micro_score(book_imb, sell_ratio, liq_imb, funding.last_funding_rate, spread)
    return MicrostructureSnapshot(
        engine=ENGINE_NAME,
        symbol=symbol,
        event_time_ms=max(depth.event_time_ms, oi.time, funding.time),
        bid_depth_quote=bid_depth,
        ask_depth_quote=ask_depth,
        spread_bps=spread,
        book_imbalance=book_imb,
        agg_trade_quote=trade_quote,
        taker_buy_quote=buy_quote,
        taker_sell_quote=sell_quote,
        taker_sell_ratio=sell_ratio,
        liquidation_buy_quote=liq_buy,
        liquidation_sell_quote=liq_sell,
        liquidation_imbalance=liq_imb,
        open_interest=oi.open_interest,
        funding_rate=funding.last_funding_rate,
        next_funding_time_ms=funding.next_funding_time,
        micro_score=score,
        notes=micro_notes(spread, sell_ratio, liq_sell + liq_buy, funding.last_funding_rate),
    )


def depth_quote(levels: tuple[tuple[str, str], ...]) -> float:
    return sum(float(price) * float(quantity) for price, quantity in levels)


def spread_bps(depth: DepthPayload) -> float:
    if not depth.bids or not depth.asks:
        return math.inf
    best_bid = float(depth.bids[0][0])
    best_ask = float(depth.asks[0][0])
    mid = (best_bid + best_ask) / 2.0
    return ((best_ask - best_bid) / mid) * 10_000.0 if mid > 0 else math.inf


def ratio_diff(left: float, right: float) -> float:
    total = left + right
    return (left - right) / total if total > 0 else 0.0


def micro_score(
    book_imbalance: float,
    sell_ratio: float,
    liquidation_imbalance: float,
    funding: float,
    spread: float,
) -> float:
    stress = 0.25 * abs(book_imbalance)
    stress += 0.25 * abs(sell_ratio - 0.5) * 2.0
    stress += 0.25 * abs(liquidation_imbalance)
    stress += 0.15 * min(1.0, abs(funding) / 0.001)
    stress += 0.10 * min(1.0, spread / 10.0)
    return min(1.0, stress)


def micro_notes(spread: float, sell_ratio: float, liquidation_quote: float, funding: float) -> tuple[str, ...]:
    notes: list[str] = []
    if spread >= 5.0:
        notes.append("wide_spread")
    if sell_ratio >= 0.70:
        notes.append("sell_taker_pressure")
    if sell_ratio <= 0.30:
        notes.append("buy_taker_pressure")
    if liquidation_quote > 0:
        notes.append("liquidation_seen")
    if abs(funding) >= 0.001:
        notes.append("funding_extreme")
    return tuple(notes)

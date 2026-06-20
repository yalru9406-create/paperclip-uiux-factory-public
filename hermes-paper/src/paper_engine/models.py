from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class SignalSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class MarketSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class FlipState(StrEnum):
    NORMAL = "NORMAL"
    RISK_OFF = "RISK_OFF"
    PANIC_SHORT = "PANIC_SHORT"
    RECOVERY_LONG = "RECOVERY_LONG"


ENGINE_NAME: Final = "paper"


@dataclass(frozen=True, slots=True)
class Kline:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    quote_volume: float
    taker_buy_quote_volume: float


@dataclass(frozen=True, slots=True)
class IndicatorRow:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    atr: float
    entry_high: float
    entry_low: float
    st_dir: int
    st_line: float


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    entry_n: int = 55
    exit_n: int = 20
    atr_n: int = 20
    st_period: int = 10
    st_mult: float = 3.0
    take_profit_r: float = 2.0
    breakout_atr_buffer: float = 0.10
    min_reward_to_cost: float = 3.0
    estimated_round_trip_cost_pct: float = 0.0015
    fee_buffer: float = 1.02
    max_initial_stop_distance_pct: float = 0.25
    min_configured_take_profit_r: float = 1.5


@dataclass(frozen=True, slots=True)
class PaperSignal:
    engine: str
    symbol: str
    side: SignalSide
    open_time_ms: int
    entry_ref: float
    close: float
    atr: float
    entry_high: float
    entry_low: float
    st_dir: int
    st_line: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PaperPosition:
    engine: str
    symbol: str
    side: SignalSide
    entry_time_ms: int
    entry_price: float
    atr: float
    stop_price: float
    take_profit_price: float
    source_signal_key: str


@dataclass(frozen=True, slots=True)
class ClosedPaperTrade:
    engine: str
    symbol: str
    side: SignalSide
    entry_time_ms: int
    exit_time_ms: int
    entry_price: float
    exit_price: float
    stop_price: float
    take_profit_price: float
    pnl_quote: float
    pnl_r: float
    reason: str
    source_signal_key: str


@dataclass(frozen=True, slots=True)
class PaperBlock:
    engine: str
    signal_key: str
    symbol: str
    side: SignalSide
    reason: str
    details: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ShadowCandidate:
    name: str
    config: StrategyConfig


@dataclass(frozen=True, slots=True)
class ShadowEvaluation:
    engine: str
    signal_key: str
    symbol: str
    side: SignalSide
    candidate: str
    allowed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FlipSnapshot:
    engine: str
    symbol: str
    open_time_ms: int
    state: FlipState
    market_stress: float
    short_flip_score: float
    recovery_long_score: float
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LiquidationEvent:
    engine: str
    symbol: str
    event_time_ms: int
    side: MarketSide
    quote_volume: float


@dataclass(frozen=True, slots=True)
class MicrostructureSnapshot:
    engine: str
    symbol: str
    event_time_ms: int
    bid_depth_quote: float
    ask_depth_quote: float
    spread_bps: float
    book_imbalance: float
    agg_trade_quote: float
    taker_buy_quote: float
    taker_sell_quote: float
    taker_sell_ratio: float
    liquidation_buy_quote: float
    liquidation_sell_quote: float
    liquidation_imbalance: float
    open_interest: float
    funding_rate: float
    next_funding_time_ms: int
    micro_score: float
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NewsEvent:
    engine: str
    symbol: str
    event_time_ms: int
    sentiment_score: float
    severity_score: float
    source: str
    headline: str


@dataclass(frozen=True, slots=True)
class NewsSnapshot:
    engine: str
    symbol: str
    event_time_ms: int
    direction_score: float
    risk_score: float
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdaptiveDecision:
    engine: str
    symbol: str
    event_time_ms: int
    target_side: SignalSide | None
    confidence: float
    trend_score: float
    micro_direction_score: float
    news_direction_score: float
    flip_direction_score: float
    allowed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PaperRunSummary:
    scanned: int
    signals: int
    opened: int
    blocked: int
    closed: int = 0
    shadow_evaluations: int = 0
    flip_alerts: int = 0
    micro_snapshots: int = 0
    adaptive_decisions: int = 0


def signal_key(signal: PaperSignal) -> str:
    return f"{signal.symbol}:{signal.open_time_ms}:{signal.side.value}"

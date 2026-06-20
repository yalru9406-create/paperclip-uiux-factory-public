from __future__ import annotations

import math
from dataclasses import dataclass
from typing import assert_never

from paper_engine.models import (
    ENGINE_NAME,
    AdaptiveDecision,
    FlipSnapshot,
    FlipState,
    MicrostructureSnapshot,
    NewsEvent,
    NewsSnapshot,
    PaperSignal,
    SignalSide,
)


@dataclass(frozen=True, slots=True)
class NewsConfig:
    lookback_ms: int = 21_600_000
    directional_threshold: float = 0.15
    high_severity_threshold: float = 0.75


@dataclass(frozen=True, slots=True)
class AdaptiveConfig:
    trend_weight: float = 0.35
    micro_weight: float = 0.35
    news_weight: float = 0.20
    flip_weight: float = 0.30
    entry_threshold: float = 0.35
    news_unclear_risk_threshold: float = 0.80
    news_direction_floor: float = 0.25
    risk_off_override_threshold: float = 0.55
    max_spread_bps: float = 12.0


@dataclass(frozen=True, slots=True)
class NewsSnapshotInput:
    symbol: str
    events: tuple[NewsEvent, ...]
    current_time_ms: int
    config: NewsConfig


@dataclass(frozen=True, slots=True)
class AdaptiveDecisionInput:
    signal: PaperSignal
    micro: MicrostructureSnapshot | None
    flip: FlipSnapshot
    news: NewsSnapshot
    config: AdaptiveConfig


@dataclass(frozen=True, slots=True)
class DecisionReasonInput:
    signal: PaperSignal
    micro: MicrostructureSnapshot | None
    flip: FlipSnapshot
    news: NewsSnapshot
    target_side: SignalSide | None
    total_score: float
    config: AdaptiveConfig


def build_news_snapshot(snapshot_input: NewsSnapshotInput) -> NewsSnapshot:
    symbol = snapshot_input.symbol
    current_time_ms = snapshot_input.current_time_ms
    config = snapshot_input.config
    relevant = tuple(
        event
        for event in snapshot_input.events
        if is_recent_relevant_event(symbol, event, current_time_ms, config)
    )
    if not relevant:
        return NewsSnapshot(ENGINE_NAME, symbol, current_time_ms, 0.0, 0.0, ("no_recent_news",))
    weighted_sum = sum(
        clamp(event.sentiment_score, -1.0, 1.0) * event_weight(event, current_time_ms, config)
        for event in relevant
    )
    total_weight = sum(event_weight(event, current_time_ms, config) for event in relevant)
    direction = weighted_sum / total_weight if total_weight > 0 else 0.0
    risk = max(clamp(event.severity_score, 0.0, 1.0) for event in relevant)
    return NewsSnapshot(
        ENGINE_NAME,
        symbol,
        current_time_ms,
        clamp(direction, -1.0, 1.0),
        risk,
        news_notes(symbol, relevant, direction, risk, config),
    )


def adaptive_decision(decision_input: AdaptiveDecisionInput) -> AdaptiveDecision:
    signal = decision_input.signal
    micro = decision_input.micro
    flip = decision_input.flip
    news = decision_input.news
    config = decision_input.config
    trend_score = side_direction(signal.side) * config.trend_weight
    micro_direction_score = micro_direction(micro) * config.micro_weight if micro is not None else 0.0
    news_direction_score = news.direction_score * config.news_weight
    flip_direction_score = flip_direction(flip) * config.flip_weight
    total_score = clamp(trend_score + micro_direction_score + news_direction_score + flip_direction_score, -1.0, 1.0)
    target_side = target_side_from_score(total_score, config.entry_threshold)
    reasons = decision_reasons(DecisionReasonInput(signal, micro, flip, news, target_side, total_score, config))
    event_time_ms = max(
        signal.open_time_ms,
        micro.event_time_ms if micro is not None else 0,
        news.event_time_ms,
        flip.open_time_ms,
    )
    return AdaptiveDecision(
        engine=ENGINE_NAME,
        symbol=signal.symbol,
        event_time_ms=event_time_ms,
        target_side=target_side,
        confidence=abs(total_score),
        trend_score=trend_score,
        micro_direction_score=micro_direction_score,
        news_direction_score=news_direction_score,
        flip_direction_score=flip_direction_score,
        allowed=len(reasons) == 0,
        reasons=tuple(reasons),
    )


def apply_adaptive_decision(signal: PaperSignal, decision: AdaptiveDecision) -> PaperSignal:
    if decision.allowed:
        return signal
    return PaperSignal(
        engine=signal.engine,
        symbol=signal.symbol,
        side=signal.side,
        open_time_ms=signal.open_time_ms,
        entry_ref=signal.entry_ref,
        close=signal.close,
        atr=signal.atr,
        entry_high=signal.entry_high,
        entry_low=signal.entry_low,
        st_dir=signal.st_dir,
        st_line=signal.st_line,
        reasons=(*signal.reasons, *decision.reasons),
    )


def is_recent_relevant_event(symbol: str, event: NewsEvent, current_time_ms: int, config: NewsConfig) -> bool:
    event_symbol = event.symbol.upper()
    target_symbol = symbol.upper()
    age_ms = current_time_ms - event.event_time_ms
    is_recent = 0 <= age_ms <= config.lookback_ms
    is_relevant = event_symbol in (target_symbol, "GLOBAL", "MARKET") or event_symbol == "BTCUSDT"
    return is_recent and is_relevant


def event_weight(event: NewsEvent, current_time_ms: int, config: NewsConfig) -> float:
    age_ratio = max(0.0, min(1.0, (current_time_ms - event.event_time_ms) / config.lookback_ms))
    recency = 1.0 - 0.5 * age_ratio
    return clamp(event.severity_score, 0.0, 1.0) * recency


def news_notes(
    symbol: str,
    events: tuple[NewsEvent, ...],
    direction: float,
    risk: float,
    config: NewsConfig,
) -> tuple[str, ...]:
    notes: list[str] = []
    if any(event.symbol.upper() == symbol.upper() for event in events):
        notes.append("symbol_news")
    if any(event.symbol.upper() in ("GLOBAL", "MARKET") for event in events):
        notes.append("global_news")
    if direction <= -config.directional_threshold:
        notes.append("negative_news")
    elif direction >= config.directional_threshold:
        notes.append("positive_news")
    else:
        notes.append("neutral_news")
    if risk >= config.high_severity_threshold:
        notes.append("high_severity_news")
    return tuple(notes)


def decision_reasons(reason_input: DecisionReasonInput) -> list[str]:
    signal = reason_input.signal
    micro = reason_input.micro
    flip = reason_input.flip
    news = reason_input.news
    target_side = reason_input.target_side
    total_score = reason_input.total_score
    config = reason_input.config
    reasons = list(signal.reasons)
    if target_side is None:
        reasons.append("adaptive_confidence_low")
    elif target_side is not signal.side:
        reasons.append("adaptive_side_conflict")
    if micro is not None and micro.spread_bps >= config.max_spread_bps:
        reasons.append("spread_too_wide")
    news_is_unclear = (
        news.risk_score >= config.news_unclear_risk_threshold
        and abs(news.direction_score) < config.news_direction_floor
    )
    if news_is_unclear:
        reasons.append("news_risk_unclear")
    if flip.state is FlipState.RISK_OFF and abs(total_score) < config.risk_off_override_threshold:
        reasons.append("btc_risk_off")
    return reasons


def micro_direction(micro: MicrostructureSnapshot) -> float:
    taker_pressure = (micro.taker_sell_ratio - 0.5) * 2.0
    funding_pressure = clamp(micro.funding_rate / 0.002, -1.0, 1.0)
    score = 0.35 * micro.book_imbalance
    score -= 0.35 * taker_pressure
    score -= 0.20 * micro.liquidation_imbalance
    score -= 0.10 * funding_pressure
    return clamp(score, -1.0, 1.0)


def flip_direction(flip: FlipSnapshot) -> float:
    match flip.state:
        case FlipState.PANIC_SHORT:
            return -1.0
        case FlipState.RECOVERY_LONG:
            return 1.0
        case FlipState.NORMAL | FlipState.RISK_OFF:
            return 0.0
    assert_never(flip.state)


def side_direction(side: SignalSide) -> float:
    match side:
        case SignalSide.LONG:
            return 1.0
        case SignalSide.SHORT:
            return -1.0
    assert_never(side)


def target_side_from_score(score: float, threshold: float) -> SignalSide | None:
    if not math.isfinite(score):
        return None
    if score >= threshold:
        return SignalSide.LONG
    if score <= -threshold:
        return SignalSide.SHORT
    return None


def clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))

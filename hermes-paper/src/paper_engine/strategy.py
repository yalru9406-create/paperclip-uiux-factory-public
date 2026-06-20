from __future__ import annotations

import math
from dataclasses import dataclass
from typing import assert_never

from paper_engine.models import ENGINE_NAME, IndicatorRow, Kline, PaperSignal, SignalSide, StrategyConfig


@dataclass(frozen=True, slots=True)
class EntryContext:
    open_time_ms: int
    entry_ref: float


def indicator_rows(bars: list[Kline], config: StrategyConfig) -> list[IndicatorRow]:
    atr_values = ewm_true_range(bars, config.atr_n)
    st_atr_values = ewm_true_range(bars, config.st_period)
    st_dirs, st_lines = supertrend(bars, st_atr_values, config)
    rows: list[IndicatorRow] = []
    for index, bar in enumerate(bars):
        entry_high = rolling_high(bars, index, config.entry_n)
        entry_low = rolling_low(bars, index, config.entry_n)
        rows.append(
            IndicatorRow(
                open_time_ms=bar.open_time_ms,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                atr=atr_values[index],
                entry_high=entry_high,
                entry_low=entry_low,
                st_dir=st_dirs[index],
                st_line=st_lines[index],
            )
        )
    return rows


def build_signal(symbol: str, row: IndicatorRow, config: StrategyConfig) -> PaperSignal | None:
    side = signal_side(row)
    if side is None:
        return None
    signal = PaperSignal(
        engine=ENGINE_NAME,
        symbol=symbol,
        side=side,
        open_time_ms=row.open_time_ms,
        entry_ref=row.open,
        close=row.close,
        atr=row.atr,
        entry_high=row.entry_high,
        entry_low=row.entry_low,
        st_dir=row.st_dir,
        st_line=row.st_line,
        reasons=(),
    )
    reasons = tuple(entry_gate_reasons(signal, config))
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
        reasons=reasons,
    )


def price_signal(signal: PaperSignal, entry: EntryContext, config: StrategyConfig) -> PaperSignal:
    priced = PaperSignal(
        engine=signal.engine,
        symbol=signal.symbol,
        side=signal.side,
        open_time_ms=entry.open_time_ms,
        entry_ref=entry.entry_ref,
        close=signal.close,
        atr=signal.atr,
        entry_high=signal.entry_high,
        entry_low=signal.entry_low,
        st_dir=signal.st_dir,
        st_line=signal.st_line,
        reasons=(),
    )
    reasons = tuple(entry_gate_reasons(priced, config))
    return PaperSignal(
        engine=priced.engine,
        symbol=priced.symbol,
        side=priced.side,
        open_time_ms=priced.open_time_ms,
        entry_ref=priced.entry_ref,
        close=priced.close,
        atr=priced.atr,
        entry_high=priced.entry_high,
        entry_low=priced.entry_low,
        st_dir=priced.st_dir,
        st_line=priced.st_line,
        reasons=reasons,
    )


def entry_gate_reasons(signal: PaperSignal, config: StrategyConfig) -> list[str]:
    reasons: list[str] = []
    if not trend_aligned(signal):
        reasons.append("supertrend_not_aligned")
    strength = breakout_strength_atr(signal)
    if strength < config.breakout_atr_buffer:
        reasons.append(f"weak_breakout_{strength:.3f}ATR_lt_{config.breakout_atr_buffer:.3f}ATR")
    reward_ratio = reward_to_cost_ratio(signal.entry_ref, signal.atr, config)
    if reward_ratio < config.min_reward_to_cost:
        reasons.append(f"reward_cost_{reward_ratio:.2f}_lt_{config.min_reward_to_cost:.2f}")
    reasons.extend(entry_geometry_reasons(signal, config))
    return reasons


def signal_side(row: IndicatorRow) -> SignalSide | None:
    if all(math.isfinite(value) for value in (row.close, row.entry_high)) and row.close > row.entry_high:
        return SignalSide.LONG
    if all(math.isfinite(value) for value in (row.close, row.entry_low)) and row.close < row.entry_low:
        return SignalSide.SHORT
    return None


def trend_aligned(signal: PaperSignal) -> bool:
    match signal.side:
        case SignalSide.LONG:
            return signal.st_dir > 0 and signal.close > signal.st_line
        case SignalSide.SHORT:
            return signal.st_dir < 0 and signal.close < signal.st_line
    assert_never(signal.side)


def breakout_strength_atr(signal: PaperSignal) -> float:
    if signal.atr <= 0:
        return 0.0
    match signal.side:
        case SignalSide.LONG:
            return max(0.0, (signal.close - signal.entry_high) / signal.atr)
        case SignalSide.SHORT:
            return max(0.0, (signal.entry_low - signal.close) / signal.atr)
    assert_never(signal.side)


def reward_to_cost_ratio(entry_ref: float, atr: float, config: StrategyConfig) -> float:
    if entry_ref <= 0 or atr <= 0:
        return 0.0
    reward_pct = config.take_profit_r * (2.0 * atr / entry_ref)
    cost_pct = config.estimated_round_trip_cost_pct * config.fee_buffer
    if cost_pct <= 0:
        return math.inf
    return reward_pct / cost_pct


def entry_geometry_reasons(signal: PaperSignal, config: StrategyConfig) -> list[str]:
    if signal.entry_ref <= 0 or signal.atr <= 0:
        return ["invalid_entry_geometry"]
    risk = 2.0 * signal.atr
    stop_distance_pct = risk / signal.entry_ref
    reasons: list[str] = []
    if stop_distance_pct > config.max_initial_stop_distance_pct:
        reasons.append(f"initial_stop_distance_{stop_distance_pct:.3f}_gt_{config.max_initial_stop_distance_pct:.3f}")
    if config.take_profit_r < config.min_configured_take_profit_r:
        reasons.append(f"risk_reward_geometry_{config.take_profit_r:.2f}R_lt_{config.min_configured_take_profit_r:.2f}R")
    target = take_profit_target(signal, risk, config.take_profit_r)
    if not math.isfinite(target) or target <= 0:
        reasons.append(f"take_profit_geometry_{config.take_profit_r:.1f}R_non_positive")
    return reasons


def take_profit_target(signal: PaperSignal, risk: float, take_profit_r: float) -> float:
    match signal.side:
        case SignalSide.LONG:
            return signal.entry_ref + risk * take_profit_r
        case SignalSide.SHORT:
            return signal.entry_ref - risk * take_profit_r
    assert_never(signal.side)


def ewm_true_range(bars: list[Kline], period: int) -> list[float]:
    values: list[float] = []
    previous_atr = math.nan
    for index, bar in enumerate(bars):
        previous_close = bars[index - 1].close if index > 0 else bar.close
        tr = max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))
        if index + 1 < period:
            values.append(math.nan)
            continue
        if math.isnan(previous_atr):
            seed = sum(true_range_at(bars, item) for item in range(index - period + 1, index + 1)) / period
            previous_atr = seed
        else:
            previous_atr = previous_atr + (tr - previous_atr) / period
        values.append(previous_atr)
    return values


def true_range_at(bars: list[Kline], index: int) -> float:
    bar = bars[index]
    previous_close = bars[index - 1].close if index > 0 else bar.close
    return max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))


def rolling_high(bars: list[Kline], index: int, period: int) -> float:
    if index < period:
        return math.nan
    return max(bar.high for bar in bars[index - period : index])


def rolling_low(bars: list[Kline], index: int, period: int) -> float:
    if index < period:
        return math.nan
    return min(bar.low for bar in bars[index - period : index])


def supertrend(bars: list[Kline], atr_values: list[float], config: StrategyConfig) -> tuple[list[int], list[float]]:
    dirs = [0 for _ in bars]
    lines = [math.nan for _ in bars]
    final_upper = [math.nan for _ in bars]
    final_lower = [math.nan for _ in bars]
    for index, bar in enumerate(bars):
        atr = atr_values[index]
        if math.isnan(atr):
            continue
        middle = (bar.high + bar.low) / 2.0
        upper = middle + config.st_mult * atr
        lower = middle - config.st_mult * atr
        if index == 0:
            final_upper[index], final_lower[index] = upper, lower
        else:
            previous_close = bars[index - 1].close
            prev_upper = final_upper[index - 1]
            prev_lower = final_lower[index - 1]
            upper_stays = math.isfinite(prev_upper) and upper >= prev_upper and previous_close <= prev_upper
            lower_stays = math.isfinite(prev_lower) and lower <= prev_lower and previous_close >= prev_lower
            final_upper[index] = prev_upper if upper_stays else upper
            final_lower[index] = prev_lower if lower_stays else lower
        previous_dir = dirs[index - 1] if index > 0 and dirs[index - 1] != 0 else 1
        if previous_dir < 0:
            dirs[index] = 1 if bar.close > final_upper[index] else -1
        else:
            dirs[index] = -1 if bar.close < final_lower[index] else 1
        lines[index] = final_lower[index] if dirs[index] > 0 else final_upper[index]
    return dirs, lines

from __future__ import annotations

from paper_engine.models import ENGINE_NAME, FlipSnapshot, FlipState, Kline


def flip_snapshot(symbol: str, bars: list[Kline]) -> FlipSnapshot:
    if len(bars) < 3:
        return FlipSnapshot(ENGINE_NAME, symbol, 0, FlipState.NORMAL, 0.0, 0.0, 0.0, ("insufficient_history",))
    recent = bars[-3:]
    first = recent[0]
    last = recent[-1]
    price_return = (last.close / first.close) - 1.0 if first.close > 0 else 0.0
    range_ratio = (last.high - last.low) / last.close if last.close > 0 else 0.0
    taker_buy_ratio = last.taker_buy_quote_volume / last.quote_volume if last.quote_volume > 0 else 0.5
    taker_sell_ratio = 1.0 - taker_buy_ratio
    market_stress = min(1.0, abs(price_return) * 5.0 + range_ratio * 2.0)
    short_flip_score = min(1.0, max(0.0, -price_return) * 6.0 + max(0.0, taker_sell_ratio - 0.5))
    recovery_long_score = min(1.0, max(0.0, price_return) * 6.0 + max(0.0, taker_buy_ratio - 0.5))
    state = flip_state(market_stress, short_flip_score, recovery_long_score)
    return FlipSnapshot(
        engine=ENGINE_NAME,
        symbol=symbol,
        open_time_ms=last.open_time_ms,
        state=state,
        market_stress=market_stress,
        short_flip_score=short_flip_score,
        recovery_long_score=recovery_long_score,
        notes=flip_notes(price_return, taker_sell_ratio, range_ratio),
    )


def flip_state(market_stress: float, short_flip_score: float, recovery_long_score: float) -> FlipState:
    if short_flip_score >= 0.75 and market_stress >= 0.35:
        return FlipState.PANIC_SHORT
    if recovery_long_score >= 0.75 and market_stress >= 0.35:
        return FlipState.RECOVERY_LONG
    if market_stress >= 0.35:
        return FlipState.RISK_OFF
    return FlipState.NORMAL


def flip_notes(price_return: float, taker_sell_ratio: float, range_ratio: float) -> tuple[str, ...]:
    notes: list[str] = []
    if price_return <= -0.03:
        notes.append("fast_downside")
    if price_return >= 0.03:
        notes.append("fast_upside")
    if taker_sell_ratio >= 0.70:
        notes.append("sell_taker_pressure")
    if range_ratio >= 0.05:
        notes.append("wide_range")
    return tuple(notes)


from __future__ import annotations

from typing import assert_never

from paper_engine.models import ENGINE_NAME, ClosedPaperTrade, Kline, PaperPosition, SignalSide


def evaluate_position_exit(position: PaperPosition, bars: list[Kline]) -> ClosedPaperTrade | None:
    risk = abs(position.entry_price - position.stop_price)
    if risk <= 0:
        return None
    for bar in bars:
        if bar.open_time_ms <= position.entry_time_ms:
            continue
        exit_price = barrier_exit_price(position, bar)
        if exit_price is None:
            continue
        pnl = side_multiplier(position.side) * (exit_price - position.entry_price)
        return ClosedPaperTrade(
            engine=ENGINE_NAME,
            symbol=position.symbol,
            side=position.side,
            entry_time_ms=position.entry_time_ms,
            exit_time_ms=bar.open_time_ms,
            entry_price=position.entry_price,
            exit_price=exit_price,
            stop_price=position.stop_price,
            take_profit_price=position.take_profit_price,
            pnl_quote=pnl,
            pnl_r=pnl / risk,
            reason=exit_reason(position, exit_price),
            source_signal_key=position.source_signal_key,
        )
    return None


def barrier_exit_price(position: PaperPosition, bar: Kline) -> float | None:
    match position.side:
        case SignalSide.LONG:
            if bar.low <= position.stop_price:
                return position.stop_price
            if bar.high >= position.take_profit_price:
                return position.take_profit_price
            return None
        case SignalSide.SHORT:
            if bar.high >= position.stop_price:
                return position.stop_price
            if bar.low <= position.take_profit_price:
                return position.take_profit_price
            return None
    assert_never(position.side)


def exit_reason(position: PaperPosition, exit_price: float) -> str:
    if exit_price == position.stop_price:
        return "STOP"
    return "TAKE_PROFIT"


def side_multiplier(side: SignalSide) -> float:
    match side:
        case SignalSide.LONG:
            return 1.0
        case SignalSide.SHORT:
            return -1.0
    assert_never(side)


from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import anyio

from paper_engine.api_models import AggTradePayload, DepthPayload, FundingPayload, OpenInterestPayload
from paper_engine.flip import flip_snapshot
from paper_engine.ledger import PaperLedger
from paper_engine.liquidation_stream import parse_force_orders
from paper_engine.micro import MicroSnapshotInput, build_micro_snapshot
from paper_engine.models import FlipState, Kline, MarketSide, PaperPosition, PaperRunSummary, SignalSide, StrategyConfig
from paper_engine.positions import evaluate_position_exit
from paper_engine.runner import PaperRunConfig, evaluate_symbol, micro_symbols
from paper_engine.shadow import shadow_candidates, shadow_rows_for_signal
from paper_engine.strategy import build_signal, entry_gate_reasons, indicator_rows


def rising_bars(count: int) -> list[Kline]:
    bars: list[Kline] = []
    for index in range(count):
        close = 100.0 + index
        bars.append(
            Kline(
                open_time_ms=index * 14_400_000,
                open=close - 0.4,
                high=close + 0.6,
                low=close - 0.8,
                close=close,
                quote_volume=1_000_000.0 + index,
                taker_buy_quote_volume=600_000.0,
            )
        )
    return bars


def test_build_signal_when_breakout_is_trend_aligned() -> None:
    # Given: enough rising candles to form an entry channel and SuperTrend direction.
    config = StrategyConfig(entry_n=8, exit_n=4, atr_n=5, st_period=5, breakout_atr_buffer=0.01)
    bars = rising_bars(25)
    bars[-1] = Kline(
        open_time_ms=bars[-1].open_time_ms,
        open=bars[-1].open,
        high=140.0,
        low=bars[-1].low,
        close=139.0,
        quote_volume=2_000_000.0,
        taker_buy_quote_volume=1_400_000.0,
    )

    # When: the paper strategy evaluates the latest completed candle.
    rows = indicator_rows(bars, config)
    signal = build_signal("TESTUSDT", rows[-1], config)

    # Then: it emits a long paper signal without touching live TAN state.
    assert signal is not None
    assert signal.engine == "paper"
    assert signal.side is SignalSide.LONG


def test_entry_gate_blocks_bad_short_geometry() -> None:
    # Given: a short signal whose configured 2R take-profit would be non-positive.
    config = StrategyConfig(entry_n=8, exit_n=4, atr_n=5, st_period=5, take_profit_r=2.0)
    bars = rising_bars(25)
    rows = indicator_rows(bars, config)
    signal = build_signal("TESTUSDT", rows[-1], config)
    assert signal is not None

    short_signal = replace(signal, side=SignalSide.SHORT, entry_ref=1.0, atr=1.0)

    # When: the entry gate checks the paper signal geometry.
    reasons = entry_gate_reasons(short_signal, config)

    # Then: impossible short take-profit geometry is blocked.
    assert any(reason.startswith("take_profit_geometry_") for reason in reasons)


def test_ledger_uses_paper_files_when_position_opens(tmp_path: Path) -> None:
    # Given: a clean paper ledger and a valid paper signal.
    config = StrategyConfig(entry_n=8, exit_n=4, atr_n=5, st_period=5, breakout_atr_buffer=0.01)
    rows = indicator_rows(rising_bars(25), config)
    signal = build_signal("TESTUSDT", rows[-1], config)
    assert signal is not None
    ledger = PaperLedger(tmp_path)

    # When: the ledger opens the signal as a paper-only position.
    position = ledger.open_position(signal, config)

    # Then: paper files are created and TAN files are not touched.
    assert position is not None
    assert (tmp_path / "paper_positions.json").exists()
    assert (tmp_path / "paper_signals.jsonl").exists()
    assert not (tmp_path / "true_turtle_bot_state.json").exists()


def test_ledger_records_paper_run_without_signal(tmp_path: Path) -> None:
    # Given: a paper-only run summary with no market signals.
    ledger = PaperLedger(tmp_path)
    summary = PaperRunSummary(scanned=5, signals=0, opened=0, blocked=0)

    # When: the run heartbeat is recorded.
    ledger.append_run(summary)

    # Then: only paper run state is written.
    assert (tmp_path / "paper_runs.jsonl").exists()
    assert not (tmp_path / "true_turtle_bot_state.json").exists()


class OneBarGateway:
    async def klines(self, symbol: str, interval: str, limit: int) -> list[Kline]:
        _ = (symbol, interval, limit)
        return rising_bars(1)


def test_evaluate_symbol_skips_new_symbol_when_kline_history_is_short() -> None:
    # Given: a newly listed futures symbol with only one 4h candle.
    config = PaperRunConfig(kline_limit=180)

    # When: the paper runner evaluates that symbol.
    signal = anyio.run(evaluate_symbol, OneBarGateway(), "REUSDT", config)

    # Then: the symbol is skipped instead of crashing the service.
    assert signal is None


def test_position_exit_records_take_profit_when_long_target_is_touched(tmp_path: Path) -> None:
    # Given: an open paper long and a later candle whose high reaches take-profit.
    position = PaperPosition(
        engine="paper",
        symbol="TESTUSDT",
        side=SignalSide.LONG,
        entry_time_ms=10,
        entry_price=100.0,
        atr=2.0,
        stop_price=96.0,
        take_profit_price=108.0,
        source_signal_key="TESTUSDT:10:LONG",
    )
    bars = [
        Kline(10, 100.0, 103.0, 99.0, 102.0, 1_000.0, 700.0),
        Kline(20, 102.0, 109.0, 101.0, 108.5, 1_000.0, 800.0),
    ]
    ledger = PaperLedger(tmp_path)
    ledger.save_positions([position])

    # When: paper exits are evaluated.
    closed = evaluate_position_exit(position, bars)
    assert closed is not None
    ledger.close_position(position, closed)

    # Then: the position is removed and a closed paper trade is recorded.
    assert ledger.load_positions() == []
    assert (tmp_path / "paper_trades.jsonl").exists()
    assert closed.reason == "TAKE_PROFIT"
    assert closed.pnl_quote == 8.0


def test_position_exit_uses_conservative_stop_when_both_barriers_touch() -> None:
    # Given: one candle touches both stop and take-profit after entry.
    position = PaperPosition(
        engine="paper",
        symbol="TESTUSDT",
        side=SignalSide.LONG,
        entry_time_ms=10,
        entry_price=100.0,
        atr=2.0,
        stop_price=96.0,
        take_profit_price=108.0,
        source_signal_key="TESTUSDT:10:LONG",
    )
    bars = [Kline(20, 100.0, 110.0, 95.0, 101.0, 1_000.0, 500.0)]

    # When: the exit evaluator sees the ambiguous candle.
    closed = evaluate_position_exit(position, bars)

    # Then: paper accounting chooses the conservative stop outcome.
    assert closed is not None
    assert closed.reason == "STOP"
    assert closed.pnl_quote == -4.0


def test_ledger_dedupes_repeated_signal_and_records_block(tmp_path: Path) -> None:
    # Given: the same valid paper signal is processed twice.
    config = StrategyConfig(entry_n=8, exit_n=4, atr_n=5, st_period=5, breakout_atr_buffer=0.01)
    rows = indicator_rows(rising_bars(25), config)
    signal = build_signal("TESTUSDT", rows[-1], config)
    assert signal is not None
    ledger = PaperLedger(tmp_path)

    # When: both attempts are recorded.
    first = ledger.open_position(signal, config)
    second = ledger.open_position(signal, config)

    # Then: only one signal line is stored and the second attempt is blocked.
    assert first is not None
    assert second is None
    signal_lines = (tmp_path / "paper_signals.jsonl").read_text(encoding="utf-8").splitlines()
    block_lines = (tmp_path / "paper_blocks.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(signal_lines) == 1
    assert len(block_lines) == 1
    assert "duplicate_signal" in block_lines[0]


def test_shadow_rows_compare_condition_candidates() -> None:
    # Given: a valid signal and the standard shadow candidate set.
    config = StrategyConfig(entry_n=8, exit_n=4, atr_n=5, st_period=5, breakout_atr_buffer=0.01)
    rows = indicator_rows(rising_bars(25), config)
    signal = build_signal("TESTUSDT", rows[-1], config)
    assert signal is not None

    # When: shadow rows are built.
    rows_by_candidate = shadow_rows_for_signal(signal, shadow_candidates(config))

    # Then: every candidate has a deterministic allowed/blocked result.
    assert {row.candidate for row in rows_by_candidate} == {
        "base",
        "cost_strict",
        "high_reward",
        "sensitive_breakout",
        "strict_breakout",
        "wide_stop",
    }
    assert all(row.signal_key == "TESTUSDT:345600000:LONG" for row in rows_by_candidate)


def test_flip_snapshot_detects_downside_panic_state() -> None:
    # Given: a fast downside move with expanding range and sell taker pressure.
    bars = [
        Kline(1, 100.0, 101.0, 99.0, 100.0, 1_000.0, 600.0),
        Kline(2, 100.0, 100.5, 94.0, 95.0, 4_000.0, 900.0),
        Kline(3, 95.0, 96.0, 88.0, 89.0, 8_000.0, 1_000.0),
    ]

    # When: the flip paper snapshot is calculated.
    snapshot = flip_snapshot("BTCUSDT", bars)

    # Then: the state is panic-short candidate, not a live order.
    assert snapshot.state is FlipState.PANIC_SHORT
    assert snapshot.engine == "paper"


def test_parse_force_orders_converts_liquidation_payload() -> None:
    # Given: a Binance forceOrder websocket payload.
    payload = (
        '{"e":"forceOrder","E":1781790000000,'
        '"o":{"s":"BTCUSDT","S":"SELL","ap":"63000.0","q":"0.50"}}'
    )

    # When: the payload is parsed.
    events = parse_force_orders(payload)

    # Then: the liquidation quote value is available for paper micro features.
    assert len(events) == 1
    assert events[0].symbol == "BTCUSDT"
    assert events[0].side is MarketSide.SELL
    assert events[0].quote_volume == 31_500.0


def test_micro_snapshot_combines_depth_trades_liquidation_oi_and_funding() -> None:
    # Given: depth, aggTrade, liquidation, OI and funding inputs for one symbol.
    depth = DepthPayload.model_validate(
        {
            "E": 30,
            "bids": (("99.0", "2.0"), ("98.0", "1.0")),
            "asks": (("101.0", "1.0"), ("102.0", "1.0")),
        }
    )
    trades = [
        AggTradePayload.model_validate({"p": "100.0", "q": "2.0", "T": 31, "m": False}),
        AggTradePayload.model_validate({"p": "99.0", "q": "3.0", "T": 32, "m": True}),
    ]
    liquidations = parse_force_orders(
        '{"e":"forceOrder","E":33,"o":{"s":"BTCUSDT","S":"SELL","ap":"95.0","q":"2.0"}}'
    )
    oi = OpenInterestPayload.model_validate({"symbol": "BTCUSDT", "openInterest": "1000.0", "time": 34})
    funding = FundingPayload.model_validate(
        {"symbol": "BTCUSDT", "lastFundingRate": "0.0012", "nextFundingTime": 40, "time": 35}
    )

    # When: the microstructure snapshot is built.
    snapshot = build_micro_snapshot(MicroSnapshotInput("BTCUSDT", depth, trades, liquidations, oi, funding))

    # Then: all requested microstructure axes are reflected.
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.bid_depth_quote == 296.0
    assert snapshot.ask_depth_quote == 203.0
    assert snapshot.taker_buy_quote == 200.0
    assert snapshot.taker_sell_quote == 297.0
    assert snapshot.liquidation_sell_quote == 190.0
    assert snapshot.open_interest == 1000.0
    assert snapshot.funding_rate == 0.0012
    assert "liquidation_seen" in snapshot.notes
    assert "funding_extreme" in snapshot.notes


def test_micro_symbols_always_include_btc_once() -> None:
    # Given: top symbols already include BTC.
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    # When: micro symbols are selected.
    selected = micro_symbols(symbols, 2)

    # Then: BTC remains first and is not duplicated.
    assert selected == ["BTCUSDT", "ETHUSDT"]

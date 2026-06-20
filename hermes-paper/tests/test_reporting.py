from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from paper_engine.ledger import PaperLedger, block_from_signal
from paper_engine.models import (
    AdaptiveDecision,
    ClosedPaperTrade,
    FlipSnapshot,
    FlipState,
    MicrostructureSnapshot,
    NewsEvent,
    PaperPosition,
    PaperSignal,
    ShadowEvaluation,
    SignalSide,
)
from paper_engine.reporting import build_report, write_report


def test_report_summarizes_trades_blocks_shadow_micro_and_flip(tmp_path: Path) -> None:
    # Given: a paper data directory with one trade, one block, shadow rows, micro rows and a flip snapshot.
    ledger = PaperLedger(tmp_path)
    position = PaperPosition("paper", "TESTUSDT", SignalSide.LONG, 10, 100.0, 2.0, 96.0, 108.0, "TEST:10:LONG")
    trade = ClosedPaperTrade(
        "paper",
        "TESTUSDT",
        SignalSide.LONG,
        10,
        20,
        100.0,
        108.0,
        96.0,
        108.0,
        8.0,
        2.0,
        "TAKE_PROFIT",
        "TEST:10:LONG",
    )
    ledger.save_positions([position])
    ledger.append_jsonl(ledger.trades_path, trade)
    signal = replace(trade_to_signal(position), reasons=("weak_breakout",))
    ledger.append_block(block_from_signal(signal, "entry_gate", signal.reasons))
    ledger.append_shadow(
        [
            ShadowEvaluation("paper", "TEST:10:LONG", "TESTUSDT", SignalSide.LONG, "base", True, ()),
            ShadowEvaluation("paper", "TEST:10:LONG", "TESTUSDT", SignalSide.LONG, "strict", False, ("blocked",)),
        ]
    )
    ledger.append_micro(
        [
            MicrostructureSnapshot(
                "paper", "LOWUSDT", 1, 1.0, 1.0, 1.0, 0.0, 10.0, 5.0, 5.0, 0.5,
                0.0, 0.0, 0.0, 1.0, 0.0, 2, 0.1, (),
            ),
            MicrostructureSnapshot(
                "paper", "HIGHUSDT", 2, 1.0, 1.0, 1.0, 0.0, 10.0, 1.0, 9.0, 0.9,
                0.0, 0.0, 0.0, 1.0, 0.0, 2, 0.8, ("sell_taker_pressure",),
            ),
        ]
    )
    ledger.append_flip(FlipSnapshot("paper", "BTCUSDT", 30, FlipState.RISK_OFF, 0.5, 0.4, 0.0, ("stress",)))
    ledger.append_adaptive(
        [
            AdaptiveDecision(
                "paper", "TESTUSDT", 30, SignalSide.LONG, 0.72, 0.35, 0.2, 0.1, 0.0, True, (),
            )
        ]
    )
    ledger.append_news(NewsEvent("paper", "GLOBAL", 30, -0.4, 0.8, "fixture", "macro shock"))

    # When: the report is built.
    report = build_report(tmp_path)

    # Then: the report exposes the highest-signal operating metrics.
    assert report.open_positions == 1
    assert report.trades.closed == 1
    assert report.trades.total_pnl_r == 2.0
    assert report.block_reasons[0].name == "entry_gate"
    assert report.shadow_candidates[0].name == "base"
    assert report.top_micro[0].symbol == "HIGHUSDT"
    assert report.latest_flip is not None
    assert report.latest_flip.state is FlipState.RISK_OFF
    assert report.top_adaptive[0].symbol == "TESTUSDT"
    assert report.top_adaptive[0].allowed is True
    assert report.latest_news[0].source == "fixture"


def test_write_report_creates_json_file(tmp_path: Path) -> None:
    # Given: an empty paper data directory.
    data_dir = tmp_path

    # When: a report is written.
    report = write_report(data_dir)

    # Then: the generated report JSON is parseable and conservative.
    raw = (data_dir / "paper_report.json").read_text(encoding="utf-8")
    assert report.trades.closed == 0
    assert '"closed": 0' in raw
    assert '"open_positions": 0' in raw


def trade_to_signal(position: PaperPosition) -> PaperSignal:
    return PaperSignal(
        engine="paper",
        symbol=position.symbol,
        side=position.side,
        open_time_ms=position.entry_time_ms,
        entry_ref=position.entry_price,
        close=position.entry_price,
        atr=position.atr,
        entry_high=position.entry_price,
        entry_low=position.entry_price,
        st_dir=1,
        st_line=position.entry_price,
        reasons=(),
    )

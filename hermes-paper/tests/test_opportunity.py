from __future__ import annotations

import os
from pathlib import Path

from paper_engine.freshness import build_paper_freshness
from paper_engine.models import FlipSnapshot, FlipState, PaperRunSummary
from paper_engine.opportunity import (
    OpportunityAlertState,
    OpportunityMonitorConfig,
    OpportunityMonitorInput,
    build_opportunity_monitor_report,
    console_safe_opportunity_message,
)
from paper_engine.reporting import (
    AdaptiveReport,
    CountRow,
    MicroReport,
    OpenPositionReport,
    PaperReport,
    TradeReport,
)


def test_build_opportunity_monitor_report_alerts_confident_paper_candidate() -> None:
    # Given: a paper report with an allowed adaptive candidate above the alert threshold.
    paper_report = PaperReport(
        latest_run=PaperRunSummary(scanned=50, signals=2, opened=0, blocked=2, closed=0),
        open_positions=1,
        open_symbols=("BNBUSDT",),
        open_position_rows=(OpenPositionReport("BNBUSDT", "SHORT", 573.8, 591.1785915951104, 539.0428168097791),),
        trades=TradeReport(3, 3, 0, 1.0, 0.0698, 6.0, 999_999.0),
        block_reasons=(CountRow("duplicate_signal", 12),),
        shadow_candidates=(),
        top_micro=(MicroReport("BNBUSDT", 0.1638, 0.1742, 0.629, 0.0, ("sell_taker_pressure",)),),
        latest_flip=FlipSnapshot("paper", "BTCUSDT", 10, FlipState.NORMAL, 0.04, 0.06, 0.0, ()),
        top_adaptive=(AdaptiveReport("BNBUSDT", "SHORT", 0.417, True, ()),),
        latest_news=(),
    )

    # When: the opportunity monitor evaluates the report.
    report = build_opportunity_monitor_report(
        OpportunityMonitorInput(paper_report, OpportunityMonitorConfig(min_confidence=0.40), None, 1_000_000)
    )

    # Then: it proposes the candidate with operator-readable price controls.
    assert report.should_alert is True
    assert report.candidate_count == 1
    assert "BNBUSDT SHORT 42%" in report.message
    assert "진입가: 573.8 | 손절가: 591.17859 | 익절가: 539.04282" in report.message
    assert "기존 LIVE BOT 계속" in report.message
    assert "live 승격은 수동 승인 전까지 보류" in report.message


def test_build_opportunity_monitor_report_uses_stricter_default_threshold() -> None:
    # Given: the current thin-sample paper evidence has a 41.7% existing-position candidate.
    paper_report = PaperReport(
        latest_run=PaperRunSummary(scanned=50, signals=3, opened=0, blocked=3, closed=0),
        open_positions=1,
        open_symbols=("BNBUSDT",),
        open_position_rows=(OpenPositionReport("BNBUSDT", "SHORT", 573.8, 591.1785915951104, 539.0428168097791),),
        trades=TradeReport(4, 3, 1, 0.75, 0.05, 5.0, 16.55),
        block_reasons=(CountRow("duplicate_signal", 15),),
        shadow_candidates=(),
        top_micro=(MicroReport("BNBUSDT", 0.28, 0.17, 0.91, 0.0, ("sell_taker_pressure",)),),
        latest_flip=FlipSnapshot("paper", "BTCUSDT", 10, FlipState.NORMAL, 0.02, 0.06, 0.0, ()),
        top_adaptive=(AdaptiveReport("BNBUSDT", "SHORT", 0.417, True, ()),),
        latest_news=(),
    )

    # When: the opportunity monitor runs with the paper-only default threshold.
    report = build_opportunity_monitor_report(
        OpportunityMonitorInput(paper_report, OpportunityMonitorConfig(), None, 1_000_000)
    )

    # Then: the thin-confidence candidate remains observable but does not trigger an alert.
    assert report.should_alert is False
    assert report.candidate_count == 0
    assert "confidence >= 45%" in report.message
    assert "좋은 조건 없음" in report.message


def test_build_opportunity_monitor_report_suppresses_duplicate_inside_cooldown() -> None:
    # Given: a report whose fingerprint has already been sent recently.
    paper_report = PaperReport(
        latest_run=PaperRunSummary(scanned=50, signals=2, opened=0, blocked=2, closed=0),
        open_positions=0,
        open_symbols=(),
        open_position_rows=(),
        trades=TradeReport(0, 0, 0, 0.0, 0.0, 0.0, 0.0),
        block_reasons=(),
        shadow_candidates=(),
        top_micro=(),
        latest_flip=None,
        top_adaptive=(AdaptiveReport("ETHUSDT", "LONG", 0.55, True, ()),),
        latest_news=(),
    )
    first = build_opportunity_monitor_report(
        OpportunityMonitorInput(paper_report, OpportunityMonitorConfig(cooldown_minutes=60), None, 1_000_000)
    )
    state = OpportunityAlertState(first.fingerprint, 1_000_000)

    # When: the same opportunity is evaluated before the cooldown expires.
    second = build_opportunity_monitor_report(
        OpportunityMonitorInput(paper_report, OpportunityMonitorConfig(cooldown_minutes=60), state, 1_030_000)
    )

    # Then: the latest report remains readable but no duplicate Discord alert is requested.
    assert second.should_alert is False
    assert second.candidate_count == 1
    assert "알림: 중복 대기" in second.message


def test_build_opportunity_monitor_report_stays_quiet_without_candidate() -> None:
    # Given: only blocked or low-confidence adaptive rows are present.
    paper_report = PaperReport(
        latest_run=PaperRunSummary(scanned=50, signals=0, opened=0, blocked=0, closed=0),
        open_positions=0,
        open_symbols=(),
        open_position_rows=(),
        trades=TradeReport(0, 0, 0, 0.0, 0.0, 0.0, 0.0),
        block_reasons=(),
        shadow_candidates=(),
        top_micro=(),
        latest_flip=None,
        top_adaptive=(
            AdaptiveReport("BTCUSDT", "FLAT", 0.70, False, ("adaptive_confidence_low",)),
            AdaptiveReport("XRPUSDT", "SHORT", 0.35, True, ()),
        ),
        latest_news=(),
    )

    # When: the opportunity monitor evaluates the report.
    report = build_opportunity_monitor_report(
        OpportunityMonitorInput(paper_report, OpportunityMonitorConfig(min_confidence=0.40), None, 1_000_000)
    )

    # Then: it reports quiet state and does not request a Discord alert.
    assert report.should_alert is False
    assert report.candidate_count == 0
    assert "좋은 조건 없음" in report.message


def test_build_opportunity_monitor_report_marks_stale_research_gate(tmp_path: Path) -> None:
    # Given: the latest research-gate artifact is older than the paper freshness window.
    latest_research = tmp_path / "paper_research_gate_latest.txt"
    _ = latest_research.write_text("generated_at_utc=2026-06-19T00:00:00Z\n", encoding="utf-8")
    old_timestamp = 1_000_000.0 - (46 * 60)
    _ = os.utime(latest_research, (old_timestamp, old_timestamp))
    paper_report = PaperReport(
        latest_run=None,
        open_positions=0,
        open_symbols=(),
        open_position_rows=(),
        trades=TradeReport(0, 0, 0, 0.0, 0.0, 0.0, 0.0),
        block_reasons=(),
        shadow_candidates=(),
        top_micro=(),
        latest_flip=None,
        top_adaptive=(),
        latest_news=(),
    )

    # When: the opportunity monitor formats its status message.
    report = build_opportunity_monitor_report(
        OpportunityMonitorInput(
            paper_report,
            OpportunityMonitorConfig(),
            None,
            1_000_000_000,
            build_paper_freshness(tmp_path, now_seconds=1_000_000.0),
        )
    )

    # Then: stale research state is visible even when there is no opportunity candidate.
    assert report.should_alert is False
    assert "freshness: research-gate=STALE age=46m max=45m" in report.message


def test_console_safe_opportunity_message_removes_emoji_for_windows_console() -> None:
    # Given: an opportunity message intended for Discord.
    message = "🛰 PAPER OPPORTUNITY WATCH\n📉 BNBUSDT SHORT\n🧯 기존 LIVE BOT 계속. live 승격은 수동 승인 전까지 보류."

    # When: the message is prepared for a legacy Windows console.
    safe_message = console_safe_opportunity_message(message)

    # Then: Korean text remains readable while unsupported emoji are removed.
    assert safe_message.startswith("PAPER OPPORTUNITY WATCH")
    assert "[SHORT] BNBUSDT SHORT" in safe_message
    assert "기존 LIVE BOT 계속" in safe_message
    assert "🛰" not in safe_message

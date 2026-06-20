from __future__ import annotations

from paper_engine.adaptive import (
    AdaptiveConfig,
    AdaptiveDecisionInput,
    NewsConfig,
    NewsSnapshotInput,
    adaptive_decision,
    apply_adaptive_decision,
    build_news_snapshot,
)
from paper_engine.models import (
    FlipSnapshot,
    FlipState,
    MicrostructureSnapshot,
    NewsEvent,
    PaperSignal,
    SignalSide,
)


def test_adaptive_blocks_long_when_downside_sources_align() -> None:
    # Given: a clean long breakout but market microstructure, news, and BTC flip state point short.
    signal = paper_signal(SignalSide.LONG)
    decision = adaptive_decision(
        AdaptiveDecisionInput(
            signal,
            bearish_micro(),
            FlipSnapshot("paper", "BTCUSDT", 1_000, FlipState.PANIC_SHORT, 0.8, 0.9, 0.0, ("fast_downside",)),
            build_news_snapshot(
                NewsSnapshotInput(
                    "BTCUSDT",
                    (NewsEvent("paper", "BTCUSDT", 1_000, -0.9, 0.9, "fixture", "exchange exploit"),),
                    1_000,
                    NewsConfig(),
                )
            ),
            AdaptiveConfig(),
        ),
    )

    # When: the adaptive paper gate is applied.
    adapted = apply_adaptive_decision(signal, decision)

    # Then: the long is blocked rather than flipped live.
    assert decision.target_side is SignalSide.SHORT
    assert decision.allowed is False
    assert "adaptive_side_conflict" in decision.reasons
    assert "adaptive_side_conflict" in adapted.reasons


def test_adaptive_allows_short_when_downside_sources_align() -> None:
    # Given: a clean short breakout with confirming market microstructure, news, and BTC flip state.
    signal = paper_signal(SignalSide.SHORT)
    decision = adaptive_decision(
        AdaptiveDecisionInput(
            signal,
            bearish_micro(),
            FlipSnapshot("paper", "BTCUSDT", 1_000, FlipState.PANIC_SHORT, 0.8, 0.9, 0.0, ("fast_downside",)),
            build_news_snapshot(
                NewsSnapshotInput(
                    "BTCUSDT",
                    (NewsEvent("paper", "BTCUSDT", 1_000, -0.9, 0.9, "fixture", "exchange exploit"),),
                    1_000,
                    NewsConfig(),
                )
            ),
            AdaptiveConfig(),
        ),
    )

    # When: the adaptive paper gate evaluates the short.
    adapted = apply_adaptive_decision(signal, decision)

    # Then: the paper engine allows the short and records the evidence score.
    assert decision.target_side is SignalSide.SHORT
    assert decision.allowed is True
    assert decision.confidence >= 0.65
    assert adapted.reasons == ()


def test_news_snapshot_uses_global_macro_event_for_alt_symbols() -> None:
    # Given: a global macro shock, not a coin-specific headline.
    event = NewsEvent("paper", "GLOBAL", 2_000, -0.7, 0.8, "fixture", "hawkish surprise")

    # When: an altcoin asks for the current news snapshot.
    snapshot = build_news_snapshot(NewsSnapshotInput("SOLUSDT", (event,), 2_000, NewsConfig()))

    # Then: the global event contributes to risk and direction for that symbol.
    assert snapshot.symbol == "SOLUSDT"
    assert snapshot.direction_score < 0.0
    assert snapshot.risk_score == 0.8
    assert "global_news" in snapshot.notes
    assert "negative_news" in snapshot.notes


def paper_signal(side: SignalSide) -> PaperSignal:
    return PaperSignal(
        engine="paper",
        symbol="BTCUSDT",
        side=side,
        open_time_ms=1_000,
        entry_ref=100.0,
        close=99.0 if side is SignalSide.SHORT else 101.0,
        atr=2.0,
        entry_high=100.0,
        entry_low=100.0,
        st_dir=-1 if side is SignalSide.SHORT else 1,
        st_line=100.0,
        reasons=(),
    )


def bearish_micro() -> MicrostructureSnapshot:
    return MicrostructureSnapshot(
        engine="paper",
        symbol="BTCUSDT",
        event_time_ms=1_000,
        bid_depth_quote=100.0,
        ask_depth_quote=500.0,
        spread_bps=2.0,
        book_imbalance=-0.67,
        agg_trade_quote=1_000.0,
        taker_buy_quote=120.0,
        taker_sell_quote=880.0,
        taker_sell_ratio=0.88,
        liquidation_buy_quote=0.0,
        liquidation_sell_quote=500.0,
        liquidation_imbalance=1.0,
        open_interest=10_000.0,
        funding_rate=0.002,
        next_funding_time_ms=2_000,
        micro_score=0.85,
        notes=("sell_taker_pressure", "liquidation_seen", "funding_extreme"),
    )

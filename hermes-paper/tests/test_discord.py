from __future__ import annotations

import pytest

from paper_engine.discord import (
    DEFAULT_PAPER_CHANNEL_ID,
    MAX_DISCORD_CONTENT,
    DiscordConfigError,
    build_paper_discord_request,
    format_paper_discord_message,
    paper_channel_id,
    route_from_env,
)
from paper_engine.models import FlipSnapshot, FlipState, NewsEvent, PaperRunSummary
from paper_engine.reporting import AdaptiveReport, CountRow, MicroReport, OpenPositionReport, PaperReport, TradeReport


def test_format_paper_discord_message_is_compact_and_paper_only() -> None:
    # Given: a paper report with the high-signal fields an operator needs at a glance.
    report = PaperReport(
        latest_run=PaperRunSummary(
            scanned=50,
            signals=4,
            opened=1,
            blocked=3,
            closed=2,
            shadow_evaluations=12,
            flip_alerts=1,
            micro_snapshots=10,
            adaptive_decisions=4,
        ),
        open_positions=2,
        open_symbols=("BTCUSDT", "ETHUSDT"),
        open_position_rows=(
            OpenPositionReport("BTCUSDT", "SHORT", 68410.0, 71220.0, 61380.0),
            OpenPositionReport("ETHUSDT", "LONG", 3540.0, 3380.0, 3860.0),
        ),
        trades=TradeReport(4, 2, 2, 0.5, 24.0, 1.2, 1.8),
        block_reasons=(CountRow("entry_gate", 3),),
        shadow_candidates=(),
        top_micro=(MicroReport("BTCUSDT", 0.82, 1.0, 0.61, 0.0001, ("sell_pressure",)),),
        latest_flip=FlipSnapshot("paper", "BTCUSDT", 10, FlipState.PANIC_SHORT, 0.9, 0.7, 0.1, ("risk",)),
        top_adaptive=(AdaptiveReport("BTCUSDT", "SHORT", 0.76, True, ("panic_short",)),),
        latest_news=(NewsEvent("paper", "GLOBAL", 10, -0.4, 0.8, "fixture", "macro shock watch"),),
    )

    # When: the report is formatted for Discord.
    message = format_paper_discord_message(report)

    # Then: the message is short, readable, and cannot be confused with live TAN.
    assert message.startswith("🧪 TAN PAPER | 실험 상태")
    assert len(message) <= MAX_DISCORD_CONTENT
    assert "신규진입: 1 | 차단: 3 | 청산: 2" in message
    assert "손익: 🟢 +1.20R / +24.00 USDT" in message
    assert "📉 BTCUSDT SHORT" in message
    assert "진입가: 68410 | 손절가: 71220 | 익절가: 61380" in message
    assert "Adaptive: BTCUSDT SHORT 76% 🟢 allow" in message
    assert "TAN LIVE" not in message


def test_format_paper_discord_message_handles_infinite_profit_factor_and_hidden_positions() -> None:
    # Given: a paper report with more open positions than the Discord body should list.
    report = PaperReport(
        latest_run=PaperRunSummary(scanned=50, signals=2, opened=0, blocked=2, closed=0),
        open_positions=6,
        open_symbols=("AUSDT", "BUSDT", "CUSDT", "DUSDT", "EUSDT", "FUSDT"),
        open_position_rows=(
            OpenPositionReport("AUSDT", "SHORT", 10.0, 11.0, 8.0),
            OpenPositionReport("BUSDT", "SHORT", 20.0, 22.0, 16.0),
            OpenPositionReport("CUSDT", "SHORT", 30.0, 33.0, 24.0),
            OpenPositionReport("DUSDT", "SHORT", 40.0, 44.0, 32.0),
            OpenPositionReport("EUSDT", "SHORT", 50.0, 55.0, 40.0),
            OpenPositionReport("FUSDT", "SHORT", 60.0, 66.0, 48.0),
        ),
        trades=TradeReport(1, 1, 0, 1.0, 3.0, 1.0, 999_999.0),
        block_reasons=(CountRow("duplicate_signal", 8), CountRow("existing_position", 2)),
        shadow_candidates=(),
        top_micro=(),
        latest_flip=None,
        top_adaptive=(),
        latest_news=(),
    )

    # When: the report is formatted for Discord.
    message = format_paper_discord_message(report)

    # Then: noisy numeric sentinels are replaced and hidden counts match visible rows.
    assert "PF ∞" in message
    assert "… 외 1개" in message
    assert "999999" not in message


def test_paper_channel_id_prefers_explicit_paper_route() -> None:
    # Given: Discord environment values that include a paper-specific channel.
    env = {"TAN_DISCORD_PAPER_CHANNEL_ID": "paper-channel", "DISCORD_CHANNEL_ID": "live-channel"}

    # When: the paper route is resolved.
    channel_id = paper_channel_id(env)

    # Then: the paper channel wins and the generic live channel is ignored.
    assert channel_id == "paper-channel"


def test_paper_channel_id_falls_back_to_olympus_paper_channel() -> None:
    # Given: no channel is configured.
    env: dict[str, str] = {}

    # When: the paper route is resolved.
    channel_id = paper_channel_id(env)

    # Then: the Olympus paper channel is used.
    assert channel_id == DEFAULT_PAPER_CHANNEL_ID


def test_route_from_env_requires_bot_token() -> None:
    # Given: a channel is present but the Discord bot token is absent.
    env = {"TAN_DISCORD_PAPER_CHANNEL_ID": "paper-channel"}

    # When / Then: route parsing rejects the incomplete configuration.
    with pytest.raises(DiscordConfigError):
        _ = route_from_env(env)


def test_build_paper_discord_request_keeps_research_text_on_paper_route() -> None:
    # Given: a research-gate message and explicit paper Discord credentials.
    env = {"DISCORD_BOT_TOKEN": "token", "TAN_DISCORD_PAPER_CHANNEL_ID": "paper-channel"}

    # When: a Discord send request is built.
    request = build_paper_discord_request("🧬 PAPER AUTO-RESEARCH GATE\n판정: RESEARCH_ONLY", env)

    # Then: the raw text is preserved and routed only to the paper channel.
    assert request.content.startswith("🧬 PAPER AUTO-RESEARCH GATE")
    assert request.route.channel_id == "paper-channel"
    assert request.route.token == "token"

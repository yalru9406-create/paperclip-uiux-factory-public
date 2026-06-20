from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict

from paper_engine.http_client import create_async_client
from paper_engine.reporting import AdaptiveReport, OpenPositionReport, PaperReport, build_report, write_report

DISCORD_API_BASE_URL: Final = "https://discord.com/api/v10"
DEFAULT_PAPER_CHANNEL_ID: Final = "1517234557227765840"
MAX_DISCORD_CONTENT: Final = 1200
DEFAULT_ENV_PATHS: Final[tuple[Path, ...]] = (
    Path("/root/.hermes/secrets/consolidated.env"),
    Path("/srv/hermes-os/secret.env"),
    Path("/srv/hermes-os/secret_binance.env"),
    Path("/root/.hermes/.env"),
)


class DiscordPayload(TypedDict):
    content: str


@dataclass(frozen=True, slots=True)
class DiscordRoute:
    token: str
    channel_id: str


@dataclass(frozen=True, slots=True)
class DiscordSendRequest:
    route: DiscordRoute
    content: str


@dataclass(frozen=True, slots=True)
class DiscordSendResult:
    channel_id: str
    status_code: int


@dataclass(frozen=True, slots=True)
class DiscordConfigError(RuntimeError):
    setting: str


def paper_channel_id(env: Mapping[str, str] | None = None, channel_id: str | None = None) -> str:
    data = os.environ if env is None else env
    return (
        (channel_id or "").strip()
        or data.get("TAN_DISCORD_PAPER_CHANNEL_ID", "").strip()
        or data.get("DISCORD_PAPER_CHANNEL_ID", "").strip()
        or DEFAULT_PAPER_CHANNEL_ID
    )


def route_from_env(env: Mapping[str, str] | None = None, channel_id: str | None = None) -> DiscordRoute:
    data: dict[str, str] = {}
    if env is None:
        data.update(os.environ)
        for path in DEFAULT_ENV_PATHS:
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for raw_line in lines:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                _ = data.setdefault(key.strip(), value.strip().strip("\"'"))
    else:
        data.update(env)
    token = data.get("DISCORD_BOT_TOKEN", "").strip()
    resolved_channel_id = paper_channel_id(data, channel_id)
    if not token:
        raise DiscordConfigError("DISCORD_BOT_TOKEN")
    if not resolved_channel_id:
        raise DiscordConfigError("TAN_DISCORD_PAPER_CHANNEL_ID")
    return DiscordRoute(token=token, channel_id=resolved_channel_id)


def build_paper_discord_request(
    content: str,
    env: Mapping[str, str] | None = None,
    channel_id: str | None = None,
) -> DiscordSendRequest:
    return DiscordSendRequest(route=route_from_env(env, channel_id), content=content)


def format_paper_discord_message(report: PaperReport) -> str:
    latest_run = report.latest_run
    run_line = "신규진입: 0 | 차단: 0 | 청산: 0"
    if latest_run is not None:
        run_line = f"신규진입: {latest_run.opened} | 차단: {latest_run.blocked} | 청산: {latest_run.closed}"
    market_line = (
        "시장: ⚪ 없음"
        if report.latest_flip is None
        else (
            f"시장: {market_icon(report.latest_flip.state.value)} {report.latest_flip.state.value} "
            f"| short={report.latest_flip.short_flip_score:.2f} recovery={report.latest_flip.recovery_long_score:.2f}"
        )
    )
    pnl_icon = "🟢" if report.trades.total_pnl_quote >= 0 else "🔴"
    lines = [
        "🧪 TAN PAPER | 실험 상태",
        f"{market_line} | {run_line}",
        (
            f"손익: {pnl_icon} {report.trades.total_pnl_r:+.2f}R / {report.trades.total_pnl_quote:+.2f} USDT "
            f"| PF {profit_factor_text(report.trades.profit_factor)} | WR {report.trades.win_rate:.0%}"
        ),
        f"열린 포지션: {report.open_positions} | {symbols_text(report.open_symbols)}",
    ]
    visible_positions = report.open_position_rows[:5]
    for row in visible_positions:
        lines.append(open_position_text(row))
    hidden_positions = max(0, report.open_positions - len(visible_positions))
    if hidden_positions > 0:
        lines.append(f"… 외 {hidden_positions}개")
    if report.top_adaptive:
        lines.append("Adaptive: " + "; ".join(adaptive_text(row) for row in report.top_adaptive[:3]))
    if report.top_micro:
        lines.append("Micro: " + "; ".join(f"{row.symbol} {row.micro_score:.2f}" for row in report.top_micro[:3]))
    if report.block_reasons:
        block_text = ", ".join(
            f"{block_icon(row.name)} {row.name} {row.count}" for row in report.block_reasons[:3]
        )
        lines.append("차단 이유: " + block_text)
    if report.latest_news:
        news = report.latest_news[-1]
        lines.append(f"뉴스: {news.symbol} {news.sentiment_score:+.2f}/{news.severity_score:.2f} {news.headline[:80]}")
    lines.append(
        "🧯 판단: 새 주문 없음. 관찰만."
        if latest_run is None or latest_run.opened == 0
        else "🧯 판단: paper 신규 진입 발생. live와 분리 관찰."
    )
    return "\n".join(lines)[:MAX_DISCORD_CONTENT]


def market_icon(state: str) -> str:
    match state:
        case "NORMAL":
            return "🟡"
        case "RISK_OFF" | "PANIC_SHORT":
            return "🔴"
        case "RECOVERY_LONG":
            return "🟢"
        case _:
            return "⚪"


def open_position_text(row: OpenPositionReport) -> str:
    match row.side:
        case "LONG":
            side_icon = "📈"
        case "SHORT":
            side_icon = "📉"
        case _:
            side_icon = "📌"
    return (
        f"{side_icon} {row.symbol} {row.side}\n"
        f"진입가: {row.entry_price:.8g} | 손절가: {row.stop_price:.8g} | 익절가: {row.take_profit_price:.8g}"
    )


def profit_factor_text(value: float) -> str:
    if value >= 999_999.0:
        return "∞"
    return f"{value:.2f}"


def block_icon(reason: str) -> str:
    match reason:
        case "duplicate_signal":
            return "🔁"
        case "existing_position":
            return "📌"
        case _:
            return "🚫"


async def send_paper_discord_message(request: DiscordSendRequest) -> DiscordSendResult:
    payload: DiscordPayload = {"content": request.content[:2000]}
    async with create_async_client(DISCORD_API_BASE_URL) as client:
        response = await client.post(
            f"/channels/{request.route.channel_id}/messages",
            json=payload,
            headers={"Authorization": f"Bot {request.route.token}"},
        )
        _ = response.raise_for_status()
    return DiscordSendResult(channel_id=request.route.channel_id, status_code=response.status_code)


async def send_paper_discord_text(
    content: str,
    env: Mapping[str, str] | None = None,
    channel_id: str | None = None,
) -> DiscordSendResult:
    return await send_paper_discord_message(build_paper_discord_request(content, env, channel_id))


async def send_paper_discord_report(
    data_dir: Path,
    env: Mapping[str, str] | None = None,
    channel_id: str | None = None,
) -> DiscordSendResult:
    report = write_report(data_dir)
    request = DiscordSendRequest(
        route=route_from_env(env, channel_id),
        content=format_paper_discord_message(report),
    )
    return await send_paper_discord_message(request)


def preview_paper_discord_report(data_dir: Path) -> str:
    return format_paper_discord_message(build_report(data_dir))


def symbols_text(symbols: tuple[str, ...]) -> str:
    if not symbols:
        return "none"
    shown = ", ".join(symbols[:5])
    return shown if len(symbols) <= 5 else f"{shown}, +{len(symbols) - 5}"


def adaptive_text(row: AdaptiveReport) -> str:
    allowed = "🟢 allow" if row.allowed else "🔴 block"
    return f"{row.symbol} {row.target_side} {row.confidence:.0%} {allowed}"

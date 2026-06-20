from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict

from pydantic import TypeAdapter, ValidationError

from paper_engine.freshness import PaperFreshness, format_freshness_summary
from paper_engine.reporting import AdaptiveReport, MicroReport, OpenPositionReport, PaperReport

SIDE_ICON: Final[dict[str, str]] = {"LONG": "📈", "SHORT": "📉"}
NO_CANDIDATE_FINGERPRINT: Final = "no-candidates"
CONSOLE_REPLACEMENTS: Final[dict[str, str]] = {
    "🛰 ": "",
    "📈": "[LONG]",
    "📉": "[SHORT]",
    "🧯": "[SCOPE]",
    "━━━━━━━━━━━━━━━": "---------------",
}


class OpportunityAlertStateJson(TypedDict):
    fingerprint: str
    alerted_at_ms: int


@dataclass(frozen=True, slots=True)
class OpportunityMonitorConfig:
    min_confidence: float = 0.45
    cooldown_minutes: int = 60
    max_candidates: int = 5


@dataclass(frozen=True, slots=True)
class OpportunityAlertState:
    fingerprint: str
    alerted_at_ms: int


@dataclass(frozen=True, slots=True)
class OpportunityCandidate:
    symbol: str
    side: str
    confidence: float
    open_position: OpenPositionReport | None
    micro: MicroReport | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OpportunityMonitorInput:
    paper_report: PaperReport
    config: OpportunityMonitorConfig
    previous_state: OpportunityAlertState | None
    now_ms: int
    freshness: PaperFreshness | None = None


@dataclass(frozen=True, slots=True)
class OpportunityMessageInput:
    paper_report: PaperReport
    candidates: tuple[OpportunityCandidate, ...]
    config: OpportunityMonitorConfig
    should_alert: bool
    freshness: PaperFreshness | None = None


@dataclass(frozen=True, slots=True)
class OpportunityMonitorReport:
    message: str
    fingerprint: str
    should_alert: bool
    candidate_count: int


def build_opportunity_monitor_report(request: OpportunityMonitorInput) -> OpportunityMonitorReport:
    candidates = opportunity_candidates(request.paper_report, request.config)
    fingerprint = opportunity_fingerprint(candidates)
    should_alert = should_send_alert(candidates, fingerprint, request)
    return OpportunityMonitorReport(
        message=format_opportunity_message(
            OpportunityMessageInput(
                paper_report=request.paper_report,
                candidates=candidates,
                config=request.config,
                should_alert=should_alert,
                freshness=request.freshness,
            )
        ),
        fingerprint=fingerprint,
        should_alert=should_alert,
        candidate_count=len(candidates),
    )


def opportunity_candidates(
    report: PaperReport,
    config: OpportunityMonitorConfig,
) -> tuple[OpportunityCandidate, ...]:
    open_by_symbol = {position.symbol: position for position in report.open_position_rows}
    micro_by_symbol = {micro.symbol: micro for micro in report.top_micro}
    candidates = tuple(
        OpportunityCandidate(
            symbol=row.symbol,
            side=row.target_side,
            confidence=row.confidence,
            open_position=open_by_symbol.get(row.symbol),
            micro=micro_by_symbol.get(row.symbol),
            reasons=row.reasons,
        )
        for row in report.top_adaptive
        if is_proposable(row, config)
    )
    return candidates[: config.max_candidates]


def is_proposable(row: AdaptiveReport, config: OpportunityMonitorConfig) -> bool:
    return row.allowed and row.target_side in SIDE_ICON and row.confidence >= config.min_confidence


def should_send_alert(
    candidates: tuple[OpportunityCandidate, ...],
    fingerprint: str,
    request: OpportunityMonitorInput,
) -> bool:
    if not candidates:
        return False
    previous_state = request.previous_state
    if previous_state is None:
        return True
    if previous_state.fingerprint != fingerprint:
        return True
    return request.now_ms - previous_state.alerted_at_ms >= request.config.cooldown_minutes * 60_000


def opportunity_fingerprint(candidates: tuple[OpportunityCandidate, ...]) -> str:
    if not candidates:
        return NO_CANDIDATE_FINGERPRINT
    source = "|".join(candidate_fingerprint_key(candidate) for candidate in candidates)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def candidate_fingerprint_key(candidate: OpportunityCandidate) -> str:
    position = candidate.open_position
    price_key = (
        "new"
        if position is None
        else f"{position.entry_price:.8g}:{position.stop_price:.8g}:{position.take_profit_price:.8g}"
    )
    return f"{candidate.symbol}:{candidate.side}:{candidate.confidence:.2f}:{price_key}"


def format_opportunity_message(request: OpportunityMessageInput) -> str:
    lines = [
        "🛰 PAPER OPPORTUNITY WATCH",
        f"알림: {alert_label(request.candidates, request.should_alert)}",
        f"기준: adaptive allow + confidence >= {request.config.min_confidence:.0%}",
        latest_run_text(request.paper_report),
        market_text(request.paper_report),
    ]
    if request.freshness is not None:
        lines.append(format_freshness_summary(request.freshness))
    lines.append("━━━━━━━━━━━━━━━")
    if request.candidates:
        for candidate in request.candidates:
            lines.extend(candidate_lines(candidate))
    else:
        lines.append("조건: 좋은 조건 없음. paper 데이터 계속 감시.")
    lines.append("🧯 제안: 기존 LIVE BOT 계속. 이 paper 후보는 연구 전용, live 승격은 수동 승인 전까지 보류.")
    return "\n".join(lines)


def alert_label(candidates: tuple[OpportunityCandidate, ...], should_alert: bool) -> str:
    if not candidates:
        return "좋은 조건 없음"
    return "신규 제안" if should_alert else "중복 대기"


def latest_run_text(report: PaperReport) -> str:
    latest = report.latest_run
    if latest is None:
        return "최근: run 데이터 없음"
    return (
        f"최근: signals={latest.signals} opened={latest.opened} blocked={latest.blocked} "
        f"closed={latest.closed} open={report.open_positions}"
    )


def market_text(report: PaperReport) -> str:
    latest_flip = report.latest_flip
    if latest_flip is None:
        return "시장: flip 데이터 없음"
    return (
        f"시장: {latest_flip.state.value} | short={latest_flip.short_flip_score:.2f} "
        f"recovery={latest_flip.recovery_long_score:.2f}"
    )


def candidate_lines(candidate: OpportunityCandidate) -> tuple[str, ...]:
    icon = SIDE_ICON[candidate.side]
    return (
        f"{icon} {candidate.symbol} {candidate.side} {candidate.confidence:.0%} | {candidate_status(candidate)}",
        price_text(candidate.open_position),
        micro_text(candidate.micro),
    )


def candidate_status(candidate: OpportunityCandidate) -> str:
    return "paper 포지션 추적" if candidate.open_position is not None else "신규 관찰 후보"


def price_text(position: OpenPositionReport | None) -> str:
    if position is None:
        return "가격: paper 진입 전. 다음 paper 신호까지 대기."
    return (
        f"진입가: {position.entry_price:.8g} | 손절가: {position.stop_price:.8g} "
        f"| 익절가: {position.take_profit_price:.8g}"
    )


def micro_text(micro: MicroReport | None) -> str:
    if micro is None:
        return "미시구조: 데이터 없음"
    return (
        f"미시구조: score={micro.micro_score:.2f} spread={micro.spread_bps:.2f}bps "
        f"sell={micro.taker_sell_ratio:.0%} funding={micro.funding_rate:+.5f}"
    )


def console_safe_opportunity_message(message: str) -> str:
    safe_message = message
    for source, replacement in CONSOLE_REPLACEMENTS.items():
        safe_message = safe_message.replace(source, replacement)
    return safe_message


def read_opportunity_state(path: Path) -> OpportunityAlertState | None:
    if not path.exists():
        return None
    try:
        return TypeAdapter(OpportunityAlertState).validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None


def write_opportunity_state(path: Path, state: OpportunityAlertState) -> None:
    payload: OpportunityAlertStateJson = {
        "fingerprint": state.fingerprint,
        "alerted_at_ms": state.alerted_at_ms,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

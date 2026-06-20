from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter, ValidationError

from paper_engine.freshness import build_paper_freshness
from paper_engine.models import (
    AdaptiveDecision,
    ClosedPaperTrade,
    FlipSnapshot,
    MicrostructureSnapshot,
    NewsEvent,
    PaperBlock,
    PaperPosition,
    PaperRunSummary,
    ShadowEvaluation,
)


@dataclass(frozen=True, slots=True)
class CountRow:
    name: str
    count: int


@dataclass(frozen=True, slots=True)
class CandidateReport:
    name: str
    allowed: int
    blocked: int


@dataclass(frozen=True, slots=True)
class TradeReport:
    closed: int
    winners: int
    losers: int
    win_rate: float
    total_pnl_quote: float
    total_pnl_r: float
    profit_factor: float


@dataclass(frozen=True, slots=True)
class MicroReport:
    symbol: str
    micro_score: float
    spread_bps: float
    taker_sell_ratio: float
    funding_rate: float
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdaptiveReport:
    symbol: str
    target_side: str
    confidence: float
    allowed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OpenPositionReport:
    symbol: str
    side: str
    entry_price: float
    stop_price: float
    take_profit_price: float


@dataclass(frozen=True, slots=True)
class PaperReport:
    latest_run: PaperRunSummary | None
    open_positions: int
    open_symbols: tuple[str, ...]
    open_position_rows: tuple[OpenPositionReport, ...]
    trades: TradeReport
    block_reasons: tuple[CountRow, ...]
    shadow_candidates: tuple[CandidateReport, ...]
    top_micro: tuple[MicroReport, ...]
    latest_flip: FlipSnapshot | None
    top_adaptive: tuple[AdaptiveReport, ...]
    latest_news: tuple[NewsEvent, ...]


T = TypeVar("T")


def build_report(data_dir: Path) -> PaperReport:
    trades = read_jsonl(data_dir / "paper_trades.jsonl", TypeAdapter(ClosedPaperTrade))
    blocks = read_jsonl(data_dir / "paper_blocks.jsonl", TypeAdapter(PaperBlock))
    shadows = read_jsonl(data_dir / "paper_shadow.jsonl", TypeAdapter(ShadowEvaluation))
    micros = read_jsonl(data_dir / "paper_micro.jsonl", TypeAdapter(MicrostructureSnapshot))
    flips = read_jsonl(data_dir / "paper_flip.jsonl", TypeAdapter(FlipSnapshot))
    adaptive = read_jsonl(data_dir / "paper_adaptive.jsonl", TypeAdapter(AdaptiveDecision))
    news = read_jsonl(data_dir / "paper_news.jsonl", TypeAdapter(NewsEvent))
    runs = read_jsonl(data_dir / "paper_runs.jsonl", TypeAdapter(PaperRunSummary))
    positions = read_positions(data_dir / "paper_positions.json")
    return PaperReport(
        latest_run=runs[-1] if runs else None,
        open_positions=len(positions),
        open_symbols=tuple(position.symbol for position in positions),
        open_position_rows=tuple(
            OpenPositionReport(
                position.symbol,
                position.side.value,
                position.entry_price,
                position.stop_price,
                position.take_profit_price,
            )
            for position in positions
        ),
        trades=trade_report(trades),
        block_reasons=count_rows(block.reason for block in blocks),
        shadow_candidates=shadow_report(shadows),
        top_micro=top_micro_report(micros),
        latest_flip=flips[-1] if flips else None,
        top_adaptive=top_adaptive_report(adaptive),
        latest_news=tuple(news[-10:]),
    )


def write_report(data_dir: Path) -> PaperReport:
    report = build_report(data_dir)
    payload = asdict(report)
    payload["freshness"] = asdict(build_paper_freshness(data_dir))
    data_dir.mkdir(parents=True, exist_ok=True)
    _ = (data_dir / "paper_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report


def read_jsonl(path: Path, adapter: TypeAdapter[T]) -> list[T]:
    if not path.exists():
        return []
    rows: list[T] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(adapter.validate_json(line))
        except ValidationError:
            continue
    return rows


def read_positions(path: Path) -> list[PaperPosition]:
    if not path.exists():
        return []
    return TypeAdapter(list[PaperPosition]).validate_json(path.read_text(encoding="utf-8"))


def trade_report(trades: list[ClosedPaperTrade]) -> TradeReport:
    winners = [trade for trade in trades if trade.pnl_quote > 0]
    losers = [trade for trade in trades if trade.pnl_quote < 0]
    gross_win = sum(trade.pnl_quote for trade in winners)
    gross_loss = abs(sum(trade.pnl_quote for trade in losers))
    closed = len(trades)
    return TradeReport(
        closed=closed,
        winners=len(winners),
        losers=len(losers),
        win_rate=(len(winners) / closed) if closed > 0 else 0.0,
        total_pnl_quote=sum(trade.pnl_quote for trade in trades),
        total_pnl_r=sum(trade.pnl_r for trade in trades),
        profit_factor=(gross_win / gross_loss) if gross_loss > 0 else (999_999.0 if gross_win > 0 else 0.0),
    )


def count_rows(values: Iterable[str]) -> tuple[CountRow, ...]:
    counter = Counter[str](values)
    return tuple(CountRow(name=name, count=count) for name, count in counter.most_common())


def shadow_report(rows: list[ShadowEvaluation]) -> tuple[CandidateReport, ...]:
    names = sorted({row.candidate for row in rows})
    reports: list[CandidateReport] = []
    for name in names:
        candidate_rows = [row for row in rows if row.candidate == name]
        allowed = sum(1 for row in candidate_rows if row.allowed)
        reports.append(CandidateReport(name=name, allowed=allowed, blocked=len(candidate_rows) - allowed))
    return tuple(reports)


def top_micro_report(rows: list[MicrostructureSnapshot]) -> tuple[MicroReport, ...]:
    latest_by_symbol: dict[str, MicrostructureSnapshot] = {}
    for row in rows:
        latest_by_symbol[row.symbol] = row
    ranked = sorted(latest_by_symbol.values(), key=lambda row: row.micro_score, reverse=True)
    return tuple(
        MicroReport(
            symbol=row.symbol,
            micro_score=row.micro_score,
            spread_bps=row.spread_bps,
            taker_sell_ratio=row.taker_sell_ratio,
            funding_rate=row.funding_rate,
            notes=row.notes,
        )
        for row in ranked[:10]
    )


def top_adaptive_report(rows: list[AdaptiveDecision]) -> tuple[AdaptiveReport, ...]:
    latest_by_symbol: dict[str, AdaptiveDecision] = {}
    for row in rows:
        latest_by_symbol[row.symbol] = row
    ranked = sorted(latest_by_symbol.values(), key=lambda row: row.confidence, reverse=True)
    return tuple(
        AdaptiveReport(
            symbol=row.symbol,
            target_side=row.target_side.value if row.target_side is not None else "FLAT",
            confidence=row.confidence,
            allowed=row.allowed,
            reasons=row.reasons,
        )
        for row in ranked[:10]
    )

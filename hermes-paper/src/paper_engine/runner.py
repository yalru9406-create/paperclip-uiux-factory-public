from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from paper_engine.adaptive import (
    AdaptiveConfig,
    AdaptiveDecisionInput,
    NewsConfig,
    NewsSnapshotInput,
    adaptive_decision,
    apply_adaptive_decision,
    build_news_snapshot,
)
from paper_engine.binance import BinanceGateway
from paper_engine.flip import flip_snapshot
from paper_engine.http_client import create_async_client
from paper_engine.ledger import PaperLedger
from paper_engine.liquidation_stream import collect_liquidations
from paper_engine.micro import MicroCollectConfig, micro_snapshot
from paper_engine.models import (
    AdaptiveDecision,
    FlipSnapshot,
    FlipState,
    Kline,
    MicrostructureSnapshot,
    PaperRunSummary,
    PaperSignal,
    StrategyConfig,
)
from paper_engine.positions import evaluate_position_exit
from paper_engine.reporting import write_report
from paper_engine.shadow import shadow_candidates, shadow_rows_for_signal
from paper_engine.strategy import EntryContext, build_signal, indicator_rows, price_signal

BINANCE_FAPI_BASE_URL = "https://fapi.binance.com"
DEFAULT_INTERVAL = "4h"
DEFAULT_KLINE_LIMIT = 180
DEFAULT_TOP_N = 50
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass(frozen=True, slots=True)
class PaperRunConfig:
    data_dir: Path = DEFAULT_DATA_DIR
    top_n: int = DEFAULT_TOP_N
    interval: str = DEFAULT_INTERVAL
    kline_limit: int = DEFAULT_KLINE_LIMIT
    strategy: StrategyConfig = StrategyConfig()
    micro_top_n: int = 10
    micro: MicroCollectConfig = MicroCollectConfig()
    adaptive: AdaptiveConfig = AdaptiveConfig()
    news: NewsConfig = NewsConfig()


class KlineGateway(Protocol):
    async def klines(self, symbol: str, interval: str, limit: int) -> list[Kline]: ...


async def run_once(config: PaperRunConfig) -> PaperRunSummary:
    ledger = PaperLedger(config.data_dir)
    async with create_async_client(BINANCE_FAPI_BASE_URL) as client:
        gateway = BinanceGateway(client)
        closed = await close_open_positions(ledger, gateway, config)
        allowed = await gateway.tradable_symbols()
        symbols = await gateway.top_symbols(allowed, config.top_n)
        micro_snapshots = await append_micro_snapshots(ledger, gateway, symbols, config)
        micro_by_symbol = {snapshot.symbol: snapshot for snapshot in micro_snapshots}
        flip = await append_flip_snapshot(ledger, gateway, config)
        news_events = ledger.load_news_events()
        signals: list[PaperSignal] = []
        decisions: list[AdaptiveDecision] = []
        opened = 0
        blocked = 0
        shadow_evaluations = 0
        for symbol in symbols:
            signal = await evaluate_symbol(gateway, symbol, config)
            if signal is None:
                continue
            micro = micro_by_symbol.get(signal.symbol)
            news = build_news_snapshot(
                NewsSnapshotInput(signal.symbol, news_events, signal_context_time_ms(signal, micro, flip), config.news)
            )
            decision = adaptive_decision(AdaptiveDecisionInput(signal, micro, flip, news, config.adaptive))
            decisions.append(decision)
            adapted_signal = apply_adaptive_decision(signal, decision)
            signals.append(adapted_signal)
            shadow_rows = shadow_rows_for_signal(adapted_signal, shadow_candidates(config.strategy))
            ledger.append_shadow(shadow_rows)
            shadow_evaluations += len(shadow_rows)
            position = ledger.open_position(adapted_signal, config.strategy)
            if position is None:
                blocked += 1
            else:
                opened += 1
        ledger.append_adaptive(decisions)
        flip_alerts = 0 if flip.state is FlipState.NORMAL else 1
        summary = PaperRunSummary(
            scanned=len(symbols),
            signals=len(signals),
            opened=opened,
            blocked=blocked,
            closed=closed,
            shadow_evaluations=shadow_evaluations,
            flip_alerts=flip_alerts,
            micro_snapshots=len(micro_snapshots),
            adaptive_decisions=len(decisions),
        )
        ledger.append_run(summary)
        _ = write_report(config.data_dir)
        return summary


async def evaluate_symbol(gateway: KlineGateway, symbol: str, config: PaperRunConfig) -> PaperSignal | None:
    bars = await gateway.klines(symbol, config.interval, config.kline_limit)
    rows = indicator_rows(bars, config.strategy)
    if len(rows) < 2:
        return None
    signal = build_signal(symbol, rows[-2], config.strategy)
    if signal is None:
        return None
    entry = EntryContext(open_time_ms=rows[-1].open_time_ms, entry_ref=rows[-1].open)
    return price_signal(signal, entry, config.strategy)


async def close_open_positions(ledger: PaperLedger, gateway: KlineGateway, config: PaperRunConfig) -> int:
    closed = 0
    for position in ledger.load_positions():
        bars = await gateway.klines(position.symbol, config.interval, config.kline_limit)
        trade = evaluate_position_exit(position, bars)
        if trade is None:
            continue
        ledger.close_position(position, trade)
        closed += 1
    return closed


async def append_flip_snapshot(ledger: PaperLedger, gateway: KlineGateway, config: PaperRunConfig) -> FlipSnapshot:
    bars = await gateway.klines("BTCUSDT", config.interval, config.kline_limit)
    snapshot = flip_snapshot("BTCUSDT", bars)
    ledger.append_flip(snapshot)
    return snapshot


async def append_micro_snapshots(
    ledger: PaperLedger,
    gateway: BinanceGateway,
    symbols: list[str],
    config: PaperRunConfig,
) -> list[MicrostructureSnapshot]:
    selected = micro_symbols(symbols, config.micro_top_n)
    liquidations = await collect_liquidations(config.micro.sample_seconds)
    snapshots: list[MicrostructureSnapshot] = []
    for symbol in selected:
        snapshots.append(await micro_snapshot(gateway, symbol, liquidations, config.micro))
    ledger.append_micro(snapshots)
    return snapshots


def micro_symbols(symbols: list[str], limit: int) -> list[str]:
    selected = ["BTCUSDT", *symbols[: max(0, limit)]]
    return list(dict.fromkeys(selected))


def signal_context_time_ms(signal: PaperSignal, micro: MicrostructureSnapshot | None, flip: FlipSnapshot) -> int:
    return max(signal.open_time_ms, micro.event_time_ms if micro is not None else 0, flip.open_time_ms)

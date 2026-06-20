from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeAlias, assert_never

from pydantic import TypeAdapter, ValidationError

from paper_engine.models import (
    ENGINE_NAME,
    AdaptiveDecision,
    ClosedPaperTrade,
    FlipSnapshot,
    MicrostructureSnapshot,
    NewsEvent,
    PaperBlock,
    PaperPosition,
    PaperRunSummary,
    PaperSignal,
    ShadowEvaluation,
    SignalSide,
    StrategyConfig,
    signal_key,
)

JsonlItem: TypeAlias = (
    PaperRunSummary
    | PaperSignal
    | ClosedPaperTrade
    | PaperBlock
    | ShadowEvaluation
    | FlipSnapshot
    | MicrostructureSnapshot
    | AdaptiveDecision
    | NewsEvent
)


@dataclass(frozen=True, slots=True)
class PaperLedger:
    root: Path

    @property
    def signals_path(self) -> Path:
        return self.root / "paper_signals.jsonl"

    @property
    def positions_path(self) -> Path:
        return self.root / "paper_positions.json"

    @property
    def runs_path(self) -> Path:
        return self.root / "paper_runs.jsonl"

    @property
    def blocks_path(self) -> Path:
        return self.root / "paper_blocks.jsonl"

    @property
    def trades_path(self) -> Path:
        return self.root / "paper_trades.jsonl"

    @property
    def shadow_path(self) -> Path:
        return self.root / "paper_shadow.jsonl"

    @property
    def flip_path(self) -> Path:
        return self.root / "paper_flip.jsonl"

    @property
    def micro_path(self) -> Path:
        return self.root / "paper_micro.jsonl"

    @property
    def adaptive_path(self) -> Path:
        return self.root / "paper_adaptive.jsonl"

    @property
    def news_path(self) -> Path:
        return self.root / "paper_news.jsonl"

    def append_run(self, summary: PaperRunSummary) -> None:
        self.append_jsonl(self.runs_path, summary)

    def append_signal(self, signal: PaperSignal) -> None:
        if signal_key(signal) not in self.known_signal_keys():
            self.append_jsonl(self.signals_path, signal)

    def open_position(self, signal: PaperSignal, config: StrategyConfig) -> PaperPosition | None:
        key = signal_key(signal)
        if key in self.known_signal_keys():
            self.append_block(block_from_signal(signal, "duplicate_signal", (key,)))
            return None
        self.append_signal(signal)
        if signal.reasons:
            self.append_block(block_from_signal(signal, "entry_gate", signal.reasons))
            return None
        positions = self.load_positions()
        if any(position.symbol == signal.symbol for position in positions):
            self.append_block(block_from_signal(signal, "existing_position", (signal.symbol,)))
            return None
        position = PaperPosition(
            engine=ENGINE_NAME,
            symbol=signal.symbol,
            side=signal.side,
            entry_time_ms=signal.open_time_ms,
            entry_price=signal.entry_ref,
            atr=signal.atr,
            stop_price=stop_price(signal),
            take_profit_price=take_profit_price(signal, config),
            source_signal_key=key,
        )
        self.save_positions([*positions, position])
        return position

    def close_position(self, position: PaperPosition, trade: ClosedPaperTrade) -> None:
        positions = [item for item in self.load_positions() if item.source_signal_key != position.source_signal_key]
        self.save_positions(positions)
        self.append_jsonl(self.trades_path, trade)

    def append_block(self, block: PaperBlock) -> None:
        if self.block_key(block) not in self.known_block_keys():
            self.append_jsonl(self.blocks_path, block)

    def append_shadow(self, rows: list[ShadowEvaluation]) -> None:
        for row in rows:
            self.append_jsonl(self.shadow_path, row)

    def append_flip(self, snapshot: FlipSnapshot) -> None:
        self.append_jsonl(self.flip_path, snapshot)

    def append_micro(self, snapshots: list[MicrostructureSnapshot]) -> None:
        for snapshot in snapshots:
            self.append_jsonl(self.micro_path, snapshot)

    def append_adaptive(self, decisions: list[AdaptiveDecision]) -> None:
        for decision in decisions:
            self.append_jsonl(self.adaptive_path, decision)

    def append_news(self, event: NewsEvent) -> None:
        self.append_jsonl(self.news_path, event)

    def load_news_events(self) -> tuple[NewsEvent, ...]:
        if not self.news_path.exists():
            return ()
        adapter = TypeAdapter(NewsEvent)
        events: list[NewsEvent] = []
        for line in self.news_path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(adapter.validate_json(line))
            except ValidationError:
                continue
        return tuple(events)

    def load_positions(self) -> list[PaperPosition]:
        if not self.positions_path.exists():
            return []
        return TypeAdapter(list[PaperPosition]).validate_json(self.positions_path.read_text(encoding="utf-8"))

    def save_positions(self, positions: list[PaperPosition]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        rows = [asdict(position) for position in positions]
        _ = self.positions_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def known_signal_keys(self) -> set[str]:
        if not self.signals_path.exists():
            return set()
        adapter = TypeAdapter(PaperSignal)
        keys: set[str] = set()
        for line in self.signals_path.read_text(encoding="utf-8").splitlines():
            try:
                keys.add(signal_key(adapter.validate_json(line)))
            except ValidationError:
                continue
        return keys

    def known_block_keys(self) -> set[str]:
        if not self.blocks_path.exists():
            return set()
        adapter = TypeAdapter(PaperBlock)
        keys: set[str] = set()
        for line in self.blocks_path.read_text(encoding="utf-8").splitlines():
            try:
                keys.add(self.block_key(adapter.validate_json(line)))
            except ValidationError:
                continue
        return keys

    def block_key(self, block: PaperBlock) -> str:
        return f"{block.signal_key}:{block.reason}"

    def append_jsonl(self, path: Path, item: JsonlItem) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            _ = handle.write(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True) + "\n")


def stop_price(signal: PaperSignal) -> float:
    match signal.side:
        case SignalSide.LONG:
            return signal.entry_ref - 2.0 * signal.atr
        case SignalSide.SHORT:
            return signal.entry_ref + 2.0 * signal.atr
    assert_never(signal.side)


def take_profit_price(signal: PaperSignal, config: StrategyConfig) -> float:
    match signal.side:
        case SignalSide.LONG:
            return signal.entry_ref + 2.0 * signal.atr * config.take_profit_r
        case SignalSide.SHORT:
            return signal.entry_ref - 2.0 * signal.atr * config.take_profit_r
    assert_never(signal.side)


def block_from_signal(signal: PaperSignal, reason: str, details: tuple[str, ...]) -> PaperBlock:
    return PaperBlock(
        engine=ENGINE_NAME,
        signal_key=signal_key(signal),
        symbol=signal.symbol,
        side=signal.side,
        reason=reason,
        details=details,
    )

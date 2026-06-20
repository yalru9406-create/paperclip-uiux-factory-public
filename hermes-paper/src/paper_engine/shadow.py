from __future__ import annotations

from dataclasses import replace

from paper_engine.models import ENGINE_NAME, PaperSignal, ShadowCandidate, ShadowEvaluation, StrategyConfig, signal_key
from paper_engine.strategy import entry_gate_reasons


def shadow_candidates(base: StrategyConfig) -> list[ShadowCandidate]:
    return [
        ShadowCandidate("base", base),
        ShadowCandidate("sensitive_breakout", replace(base, breakout_atr_buffer=min(base.breakout_atr_buffer, 0.05))),
        ShadowCandidate("strict_breakout", replace(base, breakout_atr_buffer=max(base.breakout_atr_buffer, 0.35))),
        ShadowCandidate("high_reward", replace(base, take_profit_r=max(base.take_profit_r, 3.0))),
        ShadowCandidate(
            "cost_strict",
            replace(
                base,
                min_reward_to_cost=max(base.min_reward_to_cost, 4.5),
                fee_buffer=max(base.fee_buffer, 1.20),
            ),
        ),
        ShadowCandidate("wide_stop", replace(base, max_initial_stop_distance_pct=0.40)),
    ]


def shadow_rows_for_signal(signal: PaperSignal, candidates: list[ShadowCandidate]) -> list[ShadowEvaluation]:
    rows: list[ShadowEvaluation] = []
    key = signal_key(signal)
    for candidate in candidates:
        reasons = tuple(entry_gate_reasons(signal, candidate.config))
        rows.append(
            ShadowEvaluation(
                engine=ENGINE_NAME,
                signal_key=key,
                symbol=signal.symbol,
                side=signal.side,
                candidate=candidate.name,
                allowed=not reasons,
                reasons=reasons,
            )
        )
    return rows

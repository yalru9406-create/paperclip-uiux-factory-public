from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Final

from paper_engine.reporting import PaperReport
from paper_engine.research_promotion import PromotionBundleEvaluation, evaluate_promotion_bundle
from paper_engine.research_promotion_gate import promotion_bundle_gate
from paper_engine.research_types import (
    EvidenceProfile,
    GateStatus,
    PaperGateVerdict,
    PromotionBundleStatus,
    ResearchAssessment,
    ResearchGate,
    discord_label_for,
    live_approval_for,
)

STATUS_SEVERITY: Final[dict[GateStatus, int]] = {
    GateStatus.PASS: 0,
    GateStatus.WARN: 1,
    GateStatus.FAIL: 2,
}
PRIMARY_DIRECTION: Final = "funding-aware multi-timeframe long/short rotation"


def assess_paper_rotation(
    report: PaperReport,
    evidence: EvidenceProfile,
    promotion_bundle_path: Path | None = None,
    now_utc: datetime | None = None,
) -> ResearchAssessment:
    _ = evidence
    promotion_bundle = evaluate_promotion_bundle(promotion_bundle_path, now_utc)
    effective_evidence = artifact_backed_evidence(promotion_bundle)
    gates = (
        sample_gate(report),
        performance_gate(report),
        turnover_gate(report),
        promotion_bundle_gate(promotion_bundle),
        validation_gate(effective_evidence),
        cost_gate(effective_evidence),
        regime_capacity_gate(effective_evidence),
        overfit_gate(effective_evidence),
        factor_gate(effective_evidence),
        live_scope_gate(),
    )
    worst_status = max(gates, key=lambda gate: STATUS_SEVERITY[gate.status]).status
    paper_gate_verdict = paper_gate_verdict_for(worst_status, promotion_bundle.status)
    live_approval_state = live_approval_for(paper_gate_verdict, promotion_bundle.status)
    return ResearchAssessment(
        verdict=paper_gate_verdict.value,
        primary_direction=PRIMARY_DIRECTION,
        worst_status=worst_status,
        gates=gates,
        paper_gate_verdict=paper_gate_verdict,
        promotion_bundle_status=promotion_bundle.status,
        live_approval_state=live_approval_state,
        discord_label=discord_label_for(paper_gate_verdict, live_approval_state),
    )


def artifact_backed_evidence(promotion_bundle: PromotionBundleEvaluation) -> EvidenceProfile:
    match promotion_bundle.status:  # noqa: F401  # noqa: MATCH_OK - pyright proves coverage.
        case PromotionBundleStatus.PASSING:
            return promotion_bundle.evidence_profile
        case PromotionBundleStatus.MISSING | PromotionBundleStatus.STALE | PromotionBundleStatus.FAIL:
            return EvidenceProfile()


def paper_gate_verdict_for(
    worst_status: GateStatus,
    promotion_bundle_status: PromotionBundleStatus,
) -> PaperGateVerdict:
    match (worst_status, promotion_bundle_status):  # noqa: F401  # noqa: MATCH_OK - pyright proves coverage.
        case (GateStatus.PASS, PromotionBundleStatus.PASSING):
            return PaperGateVerdict.PAPER_ROTATION_CANDIDATE
        case (GateStatus.FAIL | GateStatus.WARN, _):
            return PaperGateVerdict.RESEARCH_ONLY
        case (
            GateStatus.PASS,
            PromotionBundleStatus.MISSING | PromotionBundleStatus.STALE | PromotionBundleStatus.FAIL,
        ):
            return PaperGateVerdict.RESEARCH_ONLY


def sample_gate(report: PaperReport) -> ResearchGate:
    closed = report.trades.closed
    if closed < 30:
        return ResearchGate(
            "sample",
            GateStatus.FAIL,
            f"closed trades {closed} < 30; positive PnL is too thin for rotation research.",
            "Collect more paper trades or run historical OOS replay before changing speed.",
        )
    if closed < 100:
        return ResearchGate(
            "sample",
            GateStatus.WARN,
            f"closed trades {closed} < 100; usable for watch, not promotion.",
            "Keep paper running until sample is broad enough across regimes.",
        )
    return ResearchGate("sample", GateStatus.PASS, f"closed trades {closed} >= 100.", "Sample gate is usable.")


def performance_gate(report: PaperReport) -> ResearchGate:
    trades = report.trades
    if trades.total_pnl_r <= 0.0 or trades.total_pnl_quote <= 0.0:
        return ResearchGate(
            "performance",
            GateStatus.FAIL,
            f"paper PnL is not positive after current assumptions: {trades.total_pnl_r:.2f}R.",
            "Reject the candidate until net paper expectancy is positive.",
        )
    if trades.profit_factor < 1.5:
        return ResearchGate(
            "performance",
            GateStatus.FAIL,
            f"profit factor {trades.profit_factor:.2f} < 1.50.",
            "Improve edge or reduce turnover before any paper-fast promotion.",
        )
    return ResearchGate(
        "performance",
        GateStatus.PASS,
        f"PnL {trades.total_pnl_r:.2f}R and PF {format_profit_factor(trades.profit_factor)} clear the minimum screen.",
        "Keep checking after realistic costs are attached.",
    )


def turnover_gate(report: PaperReport) -> ResearchGate:
    latest = report.latest_run
    if latest is None:
        return ResearchGate(
            "turnover",
            GateStatus.WARN,
            "no latest run summary is available.",
            "Run one paper cycle first.",
        )
    if latest.signals == 0:
        return ResearchGate(
            "turnover",
            GateStatus.WARN,
            "latest run produced zero signals; this is not yet a rotation candidate.",
            "Test a separate 1h/15m paper candidate instead of loosening live.",
        )
    if latest.opened == 0 and report.open_positions == 0:
        return ResearchGate(
            "turnover",
            GateStatus.WARN,
            "signals exist but no open exposure remains.",
            "Inspect block reasons before changing entry frequency.",
        )
    return ResearchGate(
        "turnover",
        GateStatus.PASS,
        f"latest run signals={latest.signals}, opened={latest.opened}, open={report.open_positions}.",
        "Rotation activity is observable.",
    )


def validation_gate(evidence: EvidenceProfile) -> ResearchGate:
    missing = missing_names(
        (
            ("walk-forward", evidence.walk_forward),
            ("out-of-sample", evidence.out_of_sample),
            ("monte-carlo", evidence.monte_carlo),
        )
    )
    if missing:
        return ResearchGate(
            "validation",
            GateStatus.FAIL,
            f"missing validation evidence: {', '.join(missing)}.",
            "Run TAN walk-forward, OOS replay, and Monte Carlo before promotion.",
        )
    return ResearchGate(
        "validation",
        GateStatus.PASS,
        "walk-forward, OOS, and Monte Carlo evidence attached.",
        "Keep evidence fresh.",
    )


def cost_gate(evidence: EvidenceProfile) -> ResearchGate:
    if evidence.cost_model:
        return ResearchGate(
            "costs",
            GateStatus.PASS,
            "fee/slippage/funding model is attached.",
            "Reject variants that fail net costs.",
        )
    return ResearchGate(
        "costs",
        GateStatus.FAIL,
        "high-turnover rotation has no attached fee/slippage/funding evidence.",
        "Model taker fees, spread, slippage, funding, and delay first.",
    )


def regime_capacity_gate(evidence: EvidenceProfile) -> ResearchGate:
    missing = missing_names((("regime", evidence.regime), ("capacity", evidence.capacity)))
    if missing:
        return ResearchGate(
            "regime-capacity",
            GateStatus.FAIL,
            f"missing robustness evidence: {', '.join(missing)}.",
            "Test bull/bear/sideways/high-vol regimes and liquidity capacity.",
        )
    return ResearchGate(
        "regime-capacity",
        GateStatus.PASS,
        "regime and capacity evidence attached.",
        "Keep stress cases active.",
    )


def overfit_gate(evidence: EvidenceProfile) -> ResearchGate:
    missing = missing_names((("PBO", evidence.pbo), ("deflated-sharpe", evidence.deflated_sharpe)))
    if missing:
        return ResearchGate(
            "overfit",
            GateStatus.FAIL,
            f"missing overfit evidence: {', '.join(missing)}.",
            "Add PBO/CSCV and DSR/PSR before trusting an optimized variant.",
        )
    return ResearchGate(
        "overfit",
        GateStatus.PASS,
        "PBO and deflated Sharpe evidence attached.",
        "Avoid expanding grids without retest.",
    )


def factor_gate(evidence: EvidenceProfile) -> ResearchGate:
    if evidence.factor_exposure:
        return ResearchGate(
            "factor",
            GateStatus.PASS,
            "factor exposure evidence attached.",
            "Confirm alpha is not just BTC beta.",
        )
    return ResearchGate(
        "factor",
        GateStatus.FAIL,
        "no factor exposure check is attached.",
        "Regress returns against BTC beta, volatility, momentum, and funding proxies.",
    )


def live_scope_gate() -> ResearchGate:
    return ResearchGate(
        "scope",
        GateStatus.PASS,
        "paper research only; live 변경 금지 until a separate C5 approval.",
        "Use paper-fast or backtest artifacts, not live service mutation.",
    )


def missing_names(items: tuple[tuple[str, bool], ...]) -> tuple[str, ...]:
    return tuple(name for name, present in items if not present)


def format_profit_factor(value: float) -> str:
    if value >= 999_999.0:
        return "∞"
    return f"{value:.2f}"

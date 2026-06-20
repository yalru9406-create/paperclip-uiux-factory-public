from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from paper_engine.promotion_bundle_sources import (
    EPOCH_UTC,
    HunterInput,
    PartialPromotionMetrics,
    PromotionDecisionInput,
    PromotionInputPaths,
    ValidationRowsInput,
    candidate_row_blockers,
    passed_monte_carlo,
    passed_oos,
    passed_walk_forward,
    promotion_input_paths,
    read_model,
)
from paper_engine.research_promotion_schema import (
    PromotionArtifact,
    PromotionArtifacts,
    PromotionBundleDocument,
    PromotionMetrics,
    PromotionSourcePaths,
)
from paper_engine.research_types import (
    LiveApprovalState,
    PaperGateVerdict,
    PromotionBundleStatus,
    discord_label_for,
)

DEFAULT_INPUT_ROOT = Path("/srv/hermes-os")
DEFAULT_OUTPUT_PATH = Path("/srv/hermes-os/paper/data/promotion_bundle.json")
DEFAULT_SUMMARY_PATH = Path("/srv/hermes-os/paper/data/promotion_bundle.md")

app = typer.Typer(help="Generate artifact-backed TAN promotion bundles.")
console = Console()


def build_promotion_bundle(input_root: Path) -> PromotionBundleDocument:
    paths = promotion_input_paths(input_root)
    decision_read = read_model(paths.validation_dir / "promotion_decision.json", PromotionDecisionInput)
    comparison_read = read_model(paths.validation_dir / "tan_validation_comparison_latest.json", ValidationRowsInput)
    bridge_read = read_model(paths.validation_dir / "tan_candidate_evidence_bridge_latest.json", ValidationRowsInput)
    hunter_read = read_model(paths.reports_dir / "tan_promotion_hunter_latest.json", HunterInput)
    decision = decision_read.model
    comparison = comparison_read.model
    bridge = bridge_read.model
    hunter = hunter_read.model
    generated_at = latest_timestamp(
        (decision.generated_at_utc, comparison.generated_at, bridge.generated_at, hunter.generated_at)
    )
    candidate_id = decision.candidate_id or hunter.top_paper_candidate
    metrics, metric_blockers = promotion_metrics(decision.metrics, comparison, bridge, candidate_id)
    source_blockers = tuple(
        blocker
        for blocker in (decision_read.blocker, comparison_read.blocker, bridge_read.blocker, hunter_read.blocker)
        if blocker is not None
    )
    row_blockers = candidate_row_blockers(candidate_id, comparison, bridge)
    artifact_blockers = missing_artifact_blockers(paths)
    safety_blockers = hunter_safety_blockers(hunter)
    blockers = tuple(sorted((*source_blockers, *row_blockers, *artifact_blockers, *metric_blockers, *safety_blockers)))
    status = PromotionBundleStatus.FAIL if blockers else PromotionBundleStatus.PASSING
    paper_verdict = PaperGateVerdict.RESEARCH_ONLY if blockers else PaperGateVerdict.PAPER_ROTATION_CANDIDATE
    approval_state = LiveApprovalState.NONE if blockers else LiveApprovalState.AWAITING_C5
    return PromotionBundleDocument(
        generated_at_utc=generated_at,
        artifacts=promotion_artifacts(paths, generated_at),
        metrics=metrics,
        candidate_id=candidate_id,
        paper_gate_verdict=paper_verdict,
        promotion_bundle_status=status,
        live_approval_state=approval_state,
        discord_label=discord_label_for(paper_verdict, approval_state),
        blockers=blockers,
        source_paths=PromotionSourcePaths(
            validation_dir=paths.validation_dir.resolve(),
            reports_dir=paths.reports_dir.resolve(),
            paper_data_dir=paths.paper_data_dir.resolve(),
        ),
    )


def write_promotion_bundle(input_root: Path, output: Path, summary: Path) -> PromotionBundleDocument:
    bundle = build_promotion_bundle(input_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(bundle.model_dump_json(indent=2) + "\n", encoding="utf-8")
    _ = summary.write_text(render_summary(bundle), encoding="utf-8")
    return bundle


def promotion_artifacts(paths: PromotionInputPaths, generated_at: datetime) -> PromotionArtifacts:
    validation = paths.validation_dir
    return PromotionArtifacts(
        walk_forward=artifact(validation / "split_manifest.json", generated_at),
        wfa_results=artifact(validation / "wfa_results.parquet", generated_at),
        out_of_sample=artifact(validation / "tan_validation_comparison_latest.json", generated_at),
        monte_carlo=artifact(validation / "tan_candidate_evidence_bridge_latest.json", generated_at),
        cost_model=artifact(validation / "execution_model.yaml", generated_at),
        regime=artifact(validation / "stress_pack" / "regime_report.json", generated_at),
        capacity=artifact(validation / "liquidity_capacity_curve.csv", generated_at),
        pbo=artifact(validation / "cscv_pbo_report.json", generated_at),
        deflated_sharpe=artifact(validation / "sharpe_inference.json", generated_at),
        factor_exposure=artifact(validation / "factor_exposure_report.json", generated_at),
    )


def promotion_metrics(
    metrics: PartialPromotionMetrics,
    comparison: ValidationRowsInput,
    bridge: ValidationRowsInput,
    candidate_id: str,
) -> tuple[PromotionMetrics, tuple[str, ...]]:
    blockers: list[str] = []
    oos_passed = metrics.out_of_sample_passed
    if oos_passed is None:
        oos_passed = passed_oos(comparison, bridge, candidate_id)
    monte_carlo_passed = metrics.monte_carlo_passed
    if monte_carlo_passed is None:
        monte_carlo_passed = passed_monte_carlo(bridge, candidate_id)
    wfa = metric_float(metrics.wfa_positive_folds_ratio, "wfa_positive_folds_ratio", 0.0)
    wfa_passed = passed_walk_forward(bridge, candidate_id)
    if wfa_passed is None:
        blockers.append("missing_metric:walk_forward_passed")
    elif not wfa_passed:
        blockers.append("failing_metric:walk_forward_passed")
    pbo = metric_float(metrics.pbo, "pbo", 1.0)
    dsr = metric_float(metrics.deflated_sharpe_ratio, "deflated_sharpe_ratio", 0.0)
    blockers.extend(blocker for blocker in (wfa.blocker, pbo.blocker, dsr.blocker) if blocker is not None)
    return (
        PromotionMetrics(
            wfa_positive_folds_ratio=wfa.value,
            out_of_sample_passed=metric_bool(oos_passed, "out_of_sample_passed", blockers),
            monte_carlo_passed=metric_bool(monte_carlo_passed, "monte_carlo_passed", blockers),
            cost_model_passed=metric_bool(metrics.cost_model_passed, "cost_model_passed", blockers),
            regime_passed=metric_bool(metrics.regime_passed, "regime_passed", blockers),
            capacity_passed=metric_bool(metrics.capacity_passed, "capacity_passed", blockers),
            pbo=pbo.value,
            deflated_sharpe_ratio=dsr.value,
            factor_exposure_passed=metric_bool(metrics.factor_exposure_passed, "factor_exposure_passed", blockers),
        ),
        tuple(blockers),
    )


def artifact(path: Path, generated_at: datetime) -> PromotionArtifact:
    return PromotionArtifact(path=path.resolve(), generated_at_utc=generated_at)


def missing_artifact_blockers(paths: PromotionInputPaths) -> tuple[str, ...]:
    artifacts = promotion_artifacts(paths, EPOCH_UTC)
    items = (
        ("walk_forward", artifacts.walk_forward),
        ("wfa_results", artifacts.wfa_results),
        ("out_of_sample", artifacts.out_of_sample),
        ("monte_carlo", artifacts.monte_carlo),
        ("cost_model", artifacts.cost_model),
        ("regime", artifacts.regime),
        ("capacity", artifacts.capacity),
        ("pbo", artifacts.pbo),
        ("deflated_sharpe", artifacts.deflated_sharpe),
        ("factor_exposure", artifacts.factor_exposure),
    )
    return tuple(f"missing_artifact:{name}" for name, item in items if not item.path.is_file())


def hunter_safety_blockers(hunter: HunterInput) -> tuple[str, ...]:
    blockers: list[str] = []
    if hunter.live_runtime_mutation_allowed:
        blockers.append("unsafe_source:live_runtime_mutation_allowed")
    if hunter.runtime_mutation_performed:
        blockers.append("unsafe_source:runtime_mutation_performed")
    if hunter.orders_or_cancels_performed:
        blockers.append("unsafe_source:orders_or_cancels_performed")
    if hunter.tan_live_restart_allowed:
        blockers.append("unsafe_source:tan_live_restart_allowed")
    return tuple(blockers)


def metric_bool(value: bool | None, name: str, blockers: list[str]) -> bool:
    if value is None:
        blockers.append(f"missing_metric:{name}")
        return False
    if not value:
        blockers.append(f"failing_metric:{name}")
    return value


@dataclass(frozen=True, slots=True)
class FloatMetric:
    value: float
    blocker: str | None


def metric_float(value: float | None, name: str, fallback: float) -> FloatMetric:
    if value is None:
        return FloatMetric(value=fallback, blocker=f"missing_metric:{name}")
    return FloatMetric(value=value, blocker=None)


def latest_timestamp(values: tuple[datetime, ...]) -> datetime:
    return max(value.astimezone(UTC) for value in values)


def render_summary(bundle: PromotionBundleDocument) -> str:
    blockers = "\n".join(f"- {blocker}" for blocker in bundle.blockers) or "- none"
    return "".join(
        (
            "# TAN Promotion Bundle\n\n",
            f"- promotion_bundle_status: `{bundle.promotion_bundle_status}`\n",
            f"- paper_gate_verdict: `{bundle.paper_gate_verdict}`\n",
            f"- live_approval_state: `{bundle.live_approval_state}`\n",
            f"- discord_label: `{bundle.discord_label}`\n",
            f"- candidate_id: `{bundle.candidate_id}`\n\n",
            "## Blockers\n\n",
            f"{blockers}\n\n",
            "JSON fields are the source of truth. This bundle does not approve live mutation.\n",
        )
    )


@app.command()
def main(
    input_root: Annotated[Path, typer.Option("--input")] = DEFAULT_INPUT_ROOT,
    output: Annotated[Path, typer.Option("--output")] = DEFAULT_OUTPUT_PATH,
    summary: Annotated[Path, typer.Option("--summary")] = DEFAULT_SUMMARY_PATH,
) -> None:
    bundle = write_promotion_bundle(input_root, output, summary)
    message = (
        f"promotion bundle | status={bundle.promotion_bundle_status} "
        + f"paper_gate={bundle.paper_gate_verdict} live={bundle.live_approval_state} output={output}"
    )
    console.print(message)


if __name__ == "__main__":
    app()

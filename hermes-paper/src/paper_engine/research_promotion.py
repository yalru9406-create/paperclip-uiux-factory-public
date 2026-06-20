from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from pydantic import ValidationError
from typing_extensions import override

from paper_engine.research_promotion_schema import PromotionBundleDocument, PromotionMetrics
from paper_engine.research_types import (
    EvidenceProfile,
    LiveApprovalState,
    PromotionBundleStatus,
)

PROMOTION_BUNDLE_MAX_AGE: Final = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class PromotionBundleEvaluation:
    status: PromotionBundleStatus
    reason: str
    evidence_profile: EvidenceProfile


@dataclass(frozen=True, slots=True)
class PromotionBundleReadResult:
    bundle: PromotionBundleDocument | None
    failure: PromotionBundleEvaluation | None


def evaluate_promotion_bundle(
    promotion_bundle_path: Path | None,
    now_utc: datetime | None = None,
) -> PromotionBundleEvaluation:
    if promotion_bundle_path is None:
        return promotion_bundle_missing("promotion_bundle.json path was not provided.")
    if not promotion_bundle_path.is_file():
        return promotion_bundle_missing(f"promotion bundle missing at {promotion_bundle_path}.")
    return evaluate_existing_promotion_bundle(promotion_bundle_path, now_utc)


def evaluate_existing_promotion_bundle(
    promotion_bundle_path: Path,
    now_utc: datetime | None,
) -> PromotionBundleEvaluation:
    read_result = read_promotion_bundle(promotion_bundle_path)
    if read_result.failure is not None:
        return read_result.failure
    bundle = read_result.bundle
    if bundle is None:
        return promotion_bundle_fail("promotion bundle could not be parsed.")
    failure = promotion_bundle_failure(bundle, promotion_bundle_path, now_utc)
    if failure is not None:
        return failure
    return promotion_bundle_passing()


def read_promotion_bundle(promotion_bundle_path: Path) -> PromotionBundleReadResult:
    try:
        bundle = PromotionBundleDocument.model_validate_json(promotion_bundle_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return PromotionBundleReadResult(None, promotion_bundle_fail(f"promotion bundle could not be read: {exc}."))
    except ValidationError as exc:
        reason = f"promotion bundle schema rejected: {exc.errors()[0]['msg']}."
        return PromotionBundleReadResult(None, promotion_bundle_fail(reason))
    return PromotionBundleReadResult(bundle, None)


def promotion_bundle_failure(
    bundle: PromotionBundleDocument,
    promotion_bundle_path: Path,
    now_utc: datetime | None,
) -> PromotionBundleEvaluation | None:
    declared_failure = declared_status_failure(bundle)
    if declared_failure is not None:
        return declared_failure
    content_failure = promotion_bundle_content_failure(bundle, promotion_bundle_path, now_utc)
    if content_failure is not None:
        return content_failure
    return metric_failure(bundle.metrics)


def promotion_bundle_content_failure(
    bundle: PromotionBundleDocument,
    promotion_bundle_path: Path,
    now_utc: datetime | None,
) -> PromotionBundleEvaluation | None:
    try:
        checked_at = normalize_utc(now_utc or datetime.now(UTC))
        stale_reason = freshness_failure(bundle, checked_at)
    except PromotionBundleTimestampError as exc:
        return promotion_bundle_fail(str(exc))
    if stale_reason is not None:
        return promotion_bundle_stale(stale_reason)

    stale_bundle_file_reason = file_freshness_failure("bundle filesystem mtime", promotion_bundle_path, checked_at)
    if stale_bundle_file_reason is not None:
        return promotion_bundle_stale(stale_bundle_file_reason)

    bundle_dir = promotion_bundle_path.parent
    artifact_reason = missing_artifact_reason(bundle, bundle_dir)
    if artifact_reason is not None:
        return promotion_bundle_fail(artifact_reason)

    stale_artifact_file_reason = artifact_file_freshness_failure(bundle, bundle_dir, checked_at)
    if stale_artifact_file_reason is not None:
        return promotion_bundle_stale(stale_artifact_file_reason)

    return None


def declared_status_failure(bundle: PromotionBundleDocument) -> PromotionBundleEvaluation | None:
    reason = "promotion bundle generator blockers"
    if bundle.blockers:
        reason = f"{reason}: {', '.join(bundle.blockers)}"
    match bundle.promotion_bundle_status:  # noqa: F401  # noqa: MATCH_OK - pyright proves coverage.
        case PromotionBundleStatus.PASSING:
            if bundle.live_approval_state is LiveApprovalState.APPROVED:
                return promotion_bundle_fail("promotion bundle must not declare live approval.")
            return None
        case PromotionBundleStatus.MISSING:
            return promotion_bundle_missing(reason)
        case PromotionBundleStatus.STALE:
            return promotion_bundle_stale(reason)
        case PromotionBundleStatus.FAIL:
            return promotion_bundle_fail(reason)


def metric_failure(metrics: PromotionMetrics) -> PromotionBundleEvaluation | None:
    metric_failures = failing_metric_names(metrics)
    if metric_failures:
        return promotion_bundle_fail(f"promotion metrics below threshold: {', '.join(metric_failures)}.")
    return None


def promotion_bundle_missing(reason: str) -> PromotionBundleEvaluation:
    return PromotionBundleEvaluation(PromotionBundleStatus.MISSING, reason, EvidenceProfile())


def promotion_bundle_stale(reason: str) -> PromotionBundleEvaluation:
    return PromotionBundleEvaluation(PromotionBundleStatus.STALE, reason, EvidenceProfile())


def promotion_bundle_fail(reason: str) -> PromotionBundleEvaluation:
    return PromotionBundleEvaluation(PromotionBundleStatus.FAIL, reason, EvidenceProfile())


def promotion_bundle_passing() -> PromotionBundleEvaluation:
    return PromotionBundleEvaluation(
        PromotionBundleStatus.PASSING,
        "promotion bundle is fresh, complete, and passing.",
        EvidenceProfile(
            walk_forward=True,
            out_of_sample=True,
            monte_carlo=True,
            cost_model=True,
            regime=True,
            capacity=True,
            pbo=True,
            deflated_sharpe=True,
            factor_exposure=True,
        ),
    )


def freshness_failure(bundle: PromotionBundleDocument, checked_at: datetime) -> str | None:
    bundle_age = checked_at - normalize_utc(bundle.generated_at_utc)
    if bundle_age > PROMOTION_BUNDLE_MAX_AGE:
        return freshness_reason("bundle", bundle_age)
    for name, artifact in bundle.artifacts.named():
        artifact_age = checked_at - normalize_utc(artifact.generated_at_utc)
        if artifact_age > PROMOTION_BUNDLE_MAX_AGE:
            return freshness_reason(name, artifact_age)
    return None


def freshness_reason(name: str, age: timedelta) -> str:
    age_hours = age.total_seconds() / 3600
    max_hours = PROMOTION_BUNDLE_MAX_AGE.total_seconds() / 3600
    return f"promotion bundle stale: {name} age={age_hours:.1f}h max={max_hours:.0f}h."


def artifact_file_freshness_failure(
    bundle: PromotionBundleDocument,
    bundle_dir: Path,
    checked_at: datetime,
) -> str | None:
    for name, artifact in bundle.artifacts.named():
        artifact_path = resolved_artifact_path(artifact.path, bundle_dir)
        stale_reason = file_freshness_failure(f"{name} filesystem mtime", artifact_path, checked_at)
        if stale_reason is not None:
            return stale_reason
    return None


def file_freshness_failure(name: str, path: Path, checked_at: datetime) -> str | None:
    try:
        file_mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError as exc:
        return f"promotion bundle stale: {name} could not be read from {path}: {exc}."
    file_age = checked_at - file_mtime
    if file_age > PROMOTION_BUNDLE_MAX_AGE:
        return freshness_reason(name, file_age)
    return None


def missing_artifact_reason(bundle: PromotionBundleDocument, bundle_dir: Path) -> str | None:
    for name, artifact in bundle.artifacts.named():
        artifact_path = resolved_artifact_path(artifact.path, bundle_dir)
        if not artifact_path.is_file():
            return f"missing artifact path for {name}: {artifact_path}."
    return None


def resolved_artifact_path(path: Path, bundle_dir: Path) -> Path:
    if path.is_absolute():
        return path
    return bundle_dir / path


def failing_metric_names(metrics: PromotionMetrics) -> tuple[str, ...]:
    failures: list[str] = []
    if metrics.wfa_positive_folds_ratio < 0.60:
        failures.append("wfa_positive_folds_ratio < 0.60")
    if not metrics.out_of_sample_passed:
        failures.append("out_of_sample_passed")
    if not metrics.monte_carlo_passed:
        failures.append("monte_carlo_passed")
    if not metrics.cost_model_passed:
        failures.append("cost_model_passed")
    if not metrics.regime_passed:
        failures.append("regime_passed")
    if not metrics.capacity_passed:
        failures.append("capacity_passed")
    if metrics.pbo > 0.20:
        failures.append("pbo > 0.20")
    if metrics.deflated_sharpe_ratio < 0.95:
        failures.append("deflated_sharpe_ratio < 0.95")
    if not metrics.factor_exposure_passed:
        failures.append("factor_exposure_passed")
    return tuple(failures)


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PromotionBundleTimestampError(value)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class PromotionBundleTimestampError(Exception):
    value: datetime

    @override
    def __str__(self) -> str:
        return f"promotion bundle timestamp must be timezone-aware: {self.value!s}"

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

EPOCH_UTC = datetime(1970, 1, 1, tzinfo=UTC)
T = TypeVar("T", bound=BaseModel)


class PartialPromotionMetrics(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    wfa_positive_folds_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    out_of_sample_passed: bool | None = None
    monte_carlo_passed: bool | None = None
    cost_model_passed: bool | None = None
    regime_passed: bool | None = None
    capacity_passed: bool | None = None
    pbo: float | None = Field(default=None, ge=0.0, le=1.0)
    deflated_sharpe_ratio: float | None = Field(default=None, ge=0.0)
    factor_exposure_passed: bool | None = None


class PromotionDecisionInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    generated_at_utc: datetime = EPOCH_UTC
    candidate_id: str = ""
    metrics: PartialPromotionMetrics = Field(default_factory=PartialPromotionMetrics)


class RowEvidence(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    oos_status: str = ""
    replay_status: str = ""
    monte_carlo_passed: bool | None = None
    walk_forward_passed: bool | None = None


class ValidationRow(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    candidate_id: str = ""
    evidence: RowEvidence = Field(default_factory=RowEvidence)
    monte_carlo_status: str = ""
    oos_status: str = ""
    regime_coverage_status: str = ""


class ValidationRowsInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    generated_at: datetime = EPOCH_UTC
    rows: tuple[ValidationRow, ...] = ()


class HunterInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    generated_at: datetime = EPOCH_UTC
    top_paper_candidate: str = ""
    live_runtime_mutation_allowed: bool = False
    runtime_mutation_performed: bool = False
    orders_or_cancels_performed: bool = False
    tan_live_restart_allowed: bool = False


class PromotionInputPaths(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    root: Path
    validation_dir: Path
    reports_dir: Path
    paper_data_dir: Path


def promotion_input_paths(input_root: Path) -> PromotionInputPaths:
    return PromotionInputPaths(
        root=input_root,
        validation_dir=input_root / "data" / "tan" / "validation",
        reports_dir=input_root / "reports",
        paper_data_dir=input_root / "paper" / "data",
    )


@dataclass(frozen=True, slots=True)
class SourceRead(Generic[T]):
    model: T
    blocker: str | None


def candidate_row_blockers(
    candidate_id: str,
    comparison: ValidationRowsInput,
    bridge: ValidationRowsInput,
) -> tuple[str, ...]:
    if not candidate_id:
        return ("missing_candidate_id",)
    blockers: list[str] = []
    for source_name, rows in (
        ("tan_validation_comparison_latest.json", comparison.rows),
        ("tan_candidate_evidence_bridge_latest.json", bridge.rows),
    ):
        if any(not row.candidate_id for row in rows):
            blockers.append(f"missing_row_candidate_id:{source_name}")
        if rows and not rows_for_candidate(rows, candidate_id):
            blockers.append(f"candidate_mismatch:{source_name}")
    return tuple(blockers)


def passed_oos(comparison: ValidationRowsInput, bridge: ValidationRowsInput, candidate_id: str) -> bool | None:
    statuses = tuple(
        status
        for row in (*rows_for_candidate(comparison.rows, candidate_id), *rows_for_candidate(bridge.rows, candidate_id))
        if (status := row.evidence.oos_status or row.oos_status)
    )
    return any(passed_status(status) for status in statuses) if statuses else None


def passed_monte_carlo(bridge: ValidationRowsInput, candidate_id: str) -> bool | None:
    rows = rows_for_candidate(bridge.rows, candidate_id)
    states = tuple(
        row.evidence.monte_carlo_passed for row in rows if row.evidence.monte_carlo_passed is not None
    )
    if states:
        return any(state is True for state in states)
    statuses = tuple(row.monte_carlo_status for row in rows)
    return any(passed_status(status) for status in statuses) if statuses else None


def passed_walk_forward(bridge: ValidationRowsInput, candidate_id: str) -> bool | None:
    states = tuple(
        row.evidence.walk_forward_passed
        for row in rows_for_candidate(bridge.rows, candidate_id)
        if row.evidence.walk_forward_passed is not None
    )
    return any(state is True for state in states) if states else None


def read_model(path: Path, model_type: type[T]) -> SourceRead[T]:
    try:
        model = model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError:
        return SourceRead(model_type(), f"missing_source:{path.name}")
    except ValidationError:
        return SourceRead(model_type(), f"malformed_source:{path.name}")
    return SourceRead(model, None)


def rows_for_candidate(rows: tuple[ValidationRow, ...], candidate_id: str) -> tuple[ValidationRow, ...]:
    if not candidate_id:
        return ()
    return tuple(row for row in rows if row.candidate_id == candidate_id)


def passed_status(value: str) -> bool:
    return value.lower() in {"passed", "pass", "ok", "paper_gate_passed", "multi_regime"}

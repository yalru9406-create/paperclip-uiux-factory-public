from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from paper_engine.research_types import LiveApprovalState, PaperGateVerdict, PromotionBundleStatus


class PromotionArtifact(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    path: Path
    generated_at_utc: datetime


class PromotionArtifacts(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    walk_forward: PromotionArtifact
    wfa_results: PromotionArtifact
    out_of_sample: PromotionArtifact
    monte_carlo: PromotionArtifact
    cost_model: PromotionArtifact
    regime: PromotionArtifact
    capacity: PromotionArtifact
    pbo: PromotionArtifact
    deflated_sharpe: PromotionArtifact
    factor_exposure: PromotionArtifact

    def named(self) -> tuple[tuple[str, PromotionArtifact], ...]:
        return (
            ("walk-forward", self.walk_forward),
            ("WFA results", self.wfa_results),
            ("out-of-sample", self.out_of_sample),
            ("monte-carlo", self.monte_carlo),
            ("cost-model", self.cost_model),
            ("regime", self.regime),
            ("capacity", self.capacity),
            ("PBO", self.pbo),
            ("deflated-sharpe", self.deflated_sharpe),
            ("factor-exposure", self.factor_exposure),
        )


class PromotionMetrics(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    wfa_positive_folds_ratio: float = Field(ge=0.0, le=1.0)
    out_of_sample_passed: bool
    monte_carlo_passed: bool
    cost_model_passed: bool
    regime_passed: bool
    capacity_passed: bool
    pbo: float = Field(ge=0.0, le=1.0)
    deflated_sharpe_ratio: float = Field(ge=0.0)
    factor_exposure_passed: bool


class PromotionSourcePaths(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    validation_dir: Path | None = None
    reports_dir: Path | None = None
    paper_data_dir: Path | None = None


class PromotionBundleDocument(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    generated_at_utc: datetime
    artifacts: PromotionArtifacts
    metrics: PromotionMetrics
    candidate_id: str = ""
    paper_gate_verdict: PaperGateVerdict = PaperGateVerdict.PAPER_ROTATION_CANDIDATE
    promotion_bundle_status: PromotionBundleStatus = PromotionBundleStatus.PASSING
    live_approval_state: LiveApprovalState = LiveApprovalState.AWAITING_C5
    discord_label: str = "PROMOTE_READY - C5 승인 대기"
    blockers: tuple[str, ...] = ()
    source_paths: PromotionSourcePaths = Field(default_factory=PromotionSourcePaths)

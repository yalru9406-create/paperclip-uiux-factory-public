from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class GateStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class EvidencePreset(StrEnum):
    NONE = "none"
    MINIMUM = "minimum"
    FULL = "full"


class PaperGateVerdict(StrEnum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_ROTATION_CANDIDATE = "PAPER_ROTATION_CANDIDATE"
    REJECT = "REJECT"


class PromotionBundleStatus(StrEnum):
    MISSING = "MISSING"
    STALE = "STALE"
    FAIL = "FAIL"
    PASSING = "PASSING"


class LiveApprovalState(StrEnum):
    NONE = "NONE"
    AWAITING_C5 = "AWAITING_C5"
    APPROVED = "APPROVED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class EvidenceProfile:
    walk_forward: bool = False
    out_of_sample: bool = False
    monte_carlo: bool = False
    cost_model: bool = False
    regime: bool = False
    capacity: bool = False
    pbo: bool = False
    deflated_sharpe: bool = False
    factor_exposure: bool = False


@dataclass(frozen=True, slots=True)
class ResearchGate:
    name: str
    status: GateStatus
    detail: str
    action: str


@dataclass(frozen=True, slots=True)
class ResearchAssessment:
    verdict: str
    primary_direction: str
    worst_status: GateStatus
    gates: tuple[ResearchGate, ...]
    paper_gate_verdict: PaperGateVerdict = PaperGateVerdict.RESEARCH_ONLY
    promotion_bundle_status: PromotionBundleStatus = PromotionBundleStatus.MISSING
    live_approval_state: LiveApprovalState = LiveApprovalState.NONE
    discord_label: str = PaperGateVerdict.RESEARCH_ONLY.value


EVIDENCE_PRESETS: Final[dict[EvidencePreset, EvidenceProfile]] = {
    EvidencePreset.NONE: EvidenceProfile(),
    EvidencePreset.MINIMUM: EvidenceProfile(
        walk_forward=True,
        out_of_sample=True,
        monte_carlo=True,
        cost_model=True,
        regime=True,
        capacity=True,
    ),
    EvidencePreset.FULL: EvidenceProfile(
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
}


def evidence_from_preset(preset: EvidencePreset) -> EvidenceProfile:
    return EVIDENCE_PRESETS[preset]


def live_approval_for(
    paper_gate_verdict: PaperGateVerdict,
    promotion_bundle_status: PromotionBundleStatus,
) -> LiveApprovalState:
    match (paper_gate_verdict, promotion_bundle_status):  # noqa: F401  # noqa: MATCH_OK - pyright proves coverage.
        case (PaperGateVerdict.PAPER_ROTATION_CANDIDATE, PromotionBundleStatus.PASSING):
            return LiveApprovalState.AWAITING_C5
        case (_, PromotionBundleStatus.MISSING | PromotionBundleStatus.STALE | PromotionBundleStatus.FAIL):
            return LiveApprovalState.NONE
        case (PaperGateVerdict.RESEARCH_ONLY | PaperGateVerdict.REJECT, PromotionBundleStatus.PASSING):
            return LiveApprovalState.NONE


def discord_label_for(
    paper_gate_verdict: PaperGateVerdict,
    live_approval_state: LiveApprovalState,
) -> str:
    match (paper_gate_verdict, live_approval_state):  # noqa: F401  # noqa: MATCH_OK - pyright proves coverage.
        case (PaperGateVerdict.PAPER_ROTATION_CANDIDATE, LiveApprovalState.AWAITING_C5):
            return "PROMOTE_READY - C5 승인 대기"
        case (PaperGateVerdict.REJECT, LiveApprovalState.NONE):
            return PaperGateVerdict.REJECT.value
        case (PaperGateVerdict.RESEARCH_ONLY, LiveApprovalState.NONE):
            return PaperGateVerdict.RESEARCH_ONLY.value
        case (PaperGateVerdict.PAPER_ROTATION_CANDIDATE, LiveApprovalState.NONE):
            return PaperGateVerdict.RESEARCH_ONLY.value
        case (
            _,
            LiveApprovalState.APPROVED | LiveApprovalState.REVOKED,
        ):
            return PaperGateVerdict.RESEARCH_ONLY.value
        case (PaperGateVerdict.RESEARCH_ONLY | PaperGateVerdict.REJECT, LiveApprovalState.AWAITING_C5):
            return PaperGateVerdict.RESEARCH_ONLY.value

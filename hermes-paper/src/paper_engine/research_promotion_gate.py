from __future__ import annotations

from paper_engine.research_promotion import PromotionBundleEvaluation
from paper_engine.research_types import GateStatus, PromotionBundleStatus, ResearchGate


def promotion_bundle_gate(promotion_bundle: PromotionBundleEvaluation) -> ResearchGate:
    match promotion_bundle.status:  # noqa: F401  # noqa: MATCH_OK - pyright proves coverage.
        case PromotionBundleStatus.PASSING:
            return ResearchGate(
                "promotion-bundle",
                GateStatus.PASS,
                promotion_bundle.reason,
                "Keep promotion evidence fresh; live mutation still requires separate C5 approval.",
            )
        case PromotionBundleStatus.MISSING:
            return ResearchGate(
                "promotion-bundle",
                GateStatus.FAIL,
                promotion_bundle.reason,
                "Generate promotion_bundle.json with artifact paths before any paper rotation promotion.",
            )
        case PromotionBundleStatus.STALE:
            return ResearchGate(
                "promotion-bundle",
                GateStatus.FAIL,
                promotion_bundle.reason,
                "Regenerate validation artifacts inside the 24h promotion freshness window.",
            )
        case PromotionBundleStatus.FAIL:
            return ResearchGate(
                "promotion-bundle",
                GateStatus.FAIL,
                promotion_bundle.reason,
                "Fix the promotion bundle schema, artifact paths, or metrics before promotion.",
            )

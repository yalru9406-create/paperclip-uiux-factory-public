from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from paper_engine.models import PaperRunSummary
from paper_engine.reporting import CountRow, PaperReport, TradeReport
from paper_engine.research_gate import (
    EvidenceProfile,
    GateStatus,
    ascii_research_gate_report,
    assess_paper_rotation,
    format_research_gate_report,
)
from paper_engine.research_promotion import evaluate_promotion_bundle
from paper_engine.research_promotion_schema import PromotionBundleDocument
from paper_engine.research_types import ResearchAssessment

PROMOTION_ARTIFACTS: Final = (
    "walk_forward",
    "wfa_results",
    "out_of_sample",
    "monte_carlo",
    "cost_model",
    "regime",
    "capacity",
    "pbo",
    "deflated_sharpe",
    "factor_exposure",
)


def test_assess_paper_rotation_blocks_current_thin_positive_paper() -> None:
    # Given: a positive paper report with too few closed trades and no institutional validation evidence.
    report = PaperReport(
        latest_run=PaperRunSummary(scanned=50, signals=2, opened=0, blocked=2, closed=0),
        open_positions=4,
        open_symbols=("BNBUSDT", "SUIUSDT", "AVAXUSDT", "LABUSDT"),
        open_position_rows=(),
        trades=TradeReport(3, 3, 0, 1.0, 0.0698, 6.0, 999_999.0),
        block_reasons=(CountRow("duplicate_signal", 8), CountRow("existing_position", 2)),
        shadow_candidates=(),
        top_micro=(),
        latest_flip=None,
        top_adaptive=(),
        latest_news=(),
    )

    # When: the report is assessed as a faster long/short rotation candidate.
    assessment = assess_paper_rotation(report, EvidenceProfile())

    # Then: it stays in research-only mode despite the green headline PnL.
    assert assessment.verdict == "RESEARCH_ONLY"
    assert assessment.primary_direction == "funding-aware multi-timeframe long/short rotation"
    assert assessment.worst_status is GateStatus.FAIL
    assert "closed trades 3 < 30" in "\n".join(gate.detail for gate in assessment.gates)
    assert "walk-forward" in "\n".join(gate.detail for gate in assessment.gates)


def test_complete_promotion_bundle_yields_paper_rotation_candidate(tmp_path: Path) -> None:
    # Given: a complete promotion bundle with fresh artifact paths and passing validation metrics.
    generated_at = datetime(2026, 6, 19, 0, 0, tzinfo=UTC)
    bundle_path = write_promotion_bundle(tmp_path, generated_at)

    # When: the paper report is assessed through artifact-backed promotion evidence.
    assessment = assess_paper_rotation(
        candidate_report(),
        EvidenceProfile(),
        promotion_bundle_path=bundle_path,
        now_utc=generated_at + timedelta(hours=1),
    )

    # Then: structured fields mark a paper candidate while live mutation still awaits C5 approval.
    assert assessment.paper_gate_verdict == "PAPER_ROTATION_CANDIDATE"
    assert assessment.promotion_bundle_status == "PASSING"
    assert assessment.live_approval_state == "AWAITING_C5"
    assert assessment.discord_label == "PROMOTE_READY - C5 승인 대기"
    assert assessment.live_approval_state != "APPROVED"
    assert assessment.verdict == assessment.paper_gate_verdict


def test_stale_or_missing_bundle_fails_closed(tmp_path: Path) -> None:
    # Given: a promotion bundle path that does not exist.
    missing_assessment = assess_paper_rotation(
        candidate_report(),
        EvidenceProfile(),
        promotion_bundle_path=tmp_path / "missing" / "promotion_bundle.json",
        now_utc=datetime(2026, 6, 19, 0, 0, tzinfo=UTC),
    )

    # Then: missing artifact-backed evidence stays research-only with explicit bundle status.
    assert missing_assessment.paper_gate_verdict == "RESEARCH_ONLY"
    assert missing_assessment.promotion_bundle_status == "MISSING"
    assert missing_assessment.live_approval_state == "NONE"
    assert missing_assessment.discord_label == "RESEARCH_ONLY"

    # Given: a promotion bundle path whose JSON cannot be parsed.
    invalid_json_path = tmp_path / "invalid" / "promotion_bundle.json"
    invalid_json_path.parent.mkdir()
    _ = invalid_json_path.write_text("{not-json", encoding="utf-8")

    # When: the invalid JSON bundle is assessed.
    invalid_json_assessment = assess_paper_rotation(
        candidate_report(),
        EvidenceProfile(),
        promotion_bundle_path=invalid_json_path,
        now_utc=datetime(2026, 6, 19, 0, 0, tzinfo=UTC),
    )

    # Then: malformed JSON fails closed through structured fields, not formatted text.
    assert invalid_json_assessment.paper_gate_verdict == "RESEARCH_ONLY"
    assert invalid_json_assessment.promotion_bundle_status == "FAIL"
    assert invalid_json_assessment.live_approval_state == "NONE"
    assert "schema rejected" in promotion_gate_detail(invalid_json_assessment)

    # Given: a bundle whose artifact timestamps are older than the freshness window.
    stale_generated_at = datetime(2026, 6, 17, 23, 59, tzinfo=UTC)
    stale_bundle_path = write_promotion_bundle(tmp_path / "stale", stale_generated_at)

    # When: the stale bundle is assessed.
    stale_assessment = assess_paper_rotation(
        candidate_report(),
        EvidenceProfile(),
        promotion_bundle_path=stale_bundle_path,
        now_utc=datetime(2026, 6, 19, 0, 0, tzinfo=UTC),
    )

    # Then: stale state fails closed and includes the stale reason in a structured gate.
    assert stale_assessment.paper_gate_verdict == "RESEARCH_ONLY"
    assert stale_assessment.promotion_bundle_status == "STALE"
    assert stale_assessment.live_approval_state == "NONE"
    assert "stale" in promotion_gate_detail(stale_assessment)

    # Given: a fresh bundle that references an artifact path that is not present.
    malformed_bundle_path = write_promotion_bundle(tmp_path / "malformed", datetime(2026, 6, 19, 0, 0, tzinfo=UTC))
    missing_artifact = tmp_path / "malformed" / "artifacts" / "pbo.txt"
    missing_artifact.unlink()

    # When: the malformed bundle is assessed.
    malformed_assessment = assess_paper_rotation(
        candidate_report(),
        EvidenceProfile(),
        promotion_bundle_path=malformed_bundle_path,
        now_utc=datetime(2026, 6, 19, 1, 0, tzinfo=UTC),
    )

    # Then: invalid artifact paths fail closed and never imply live approval.
    assert malformed_assessment.paper_gate_verdict == "RESEARCH_ONLY"
    assert malformed_assessment.promotion_bundle_status == "FAIL"
    assert malformed_assessment.live_approval_state == "NONE"
    assert "missing artifact path" in promotion_gate_detail(malformed_assessment)


def test_cached_artifact_filesystem_mtime_fails_closed(tmp_path: Path) -> None:
    # Given: fresh JSON timestamps whose cached bundle and artifact files are 48 hours old on disk.
    generated_at = datetime(2026, 6, 20, 0, 0, tzinfo=UTC)
    bundle_path = write_promotion_bundle(tmp_path, generated_at)
    stale_mtime = (generated_at - timedelta(hours=48)).timestamp()
    os.utime(bundle_path, (stale_mtime, stale_mtime))
    for artifact_path in (tmp_path / "artifacts").iterdir():
        os.utime(artifact_path, (stale_mtime, stale_mtime))

    # When: the promotion bundle is assessed at the fresh content timestamp.
    assessment = assess_paper_rotation(
        candidate_report(),
        EvidenceProfile(),
        promotion_bundle_path=bundle_path,
        now_utc=generated_at,
    )

    # Then: filesystem staleness fails closed and cannot be promoted by fresh JSON content.
    assert assessment.paper_gate_verdict == "RESEARCH_ONLY"
    assert assessment.promotion_bundle_status in {"STALE", "FAIL"}
    assert assessment.promotion_bundle_status != "PASSING"
    assert assessment.live_approval_state == "NONE"
    assert "filesystem" in promotion_gate_detail(assessment)


def test_promotion_bundle_missing_wfa_results_field_fails_closed(tmp_path: Path) -> None:
    # Given: a syntactically valid bundle with the required WFA results slot removed.
    generated_at = datetime(2026, 6, 20, 0, 0, tzinfo=UTC)
    bundle_path = write_promotion_bundle(tmp_path, generated_at)
    bundle = PromotionBundleDocument.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    _ = bundle_path.write_text(
        bundle.model_dump_json(exclude={"artifacts": {"wfa_results"}}),
        encoding="utf-8",
    )

    # When: the downstream promotion evaluator reads the incomplete bundle.
    result = evaluate_promotion_bundle(bundle_path, datetime(2026, 6, 20, 1, 0, tzinfo=UTC))

    # Then: missing WFA result evidence fails closed instead of preserving compatibility.
    assert result.status == "FAIL"
    assert "schema rejected" in result.reason


def test_assess_paper_rotation_blocks_boolean_only_evidence() -> None:
    # Given: a candidate with enough paper sample and legacy boolean robustness evidence.
    evidence = EvidenceProfile(
        walk_forward=True,
        out_of_sample=True,
        monte_carlo=True,
        cost_model=True,
        regime=True,
        capacity=True,
        pbo=True,
        deflated_sharpe=True,
        factor_exposure=True,
    )

    # When: the report is assessed without an artifact-backed promotion bundle.
    assessment = assess_paper_rotation(candidate_report(), evidence)

    # Then: missing artifacts fail closed even when legacy booleans are all true.
    assert assessment.paper_gate_verdict == "RESEARCH_ONLY"
    assert assessment.promotion_bundle_status == "MISSING"
    assert assessment.live_approval_state == "NONE"
    assert assessment.worst_status is GateStatus.FAIL


def test_format_research_gate_report_is_operator_readable() -> None:
    # Given: a blocked assessment with one failing gate.
    report = PaperReport(
        latest_run=None,
        open_positions=0,
        open_symbols=(),
        open_position_rows=(),
        trades=TradeReport(0, 0, 0, 0.0, 0.0, 0.0, 0.0),
        block_reasons=(),
        shadow_candidates=(),
        top_micro=(),
        latest_flip=None,
        top_adaptive=(),
        latest_news=(),
    )
    assessment = assess_paper_rotation(report, EvidenceProfile())

    # When: the assessment is formatted for CLI/Discord copy-paste.
    message = format_research_gate_report(assessment)

    # Then: the text explains the judgment without implying live approval.
    assert message.startswith("🧬 PAPER AUTO-RESEARCH GATE")
    assert "판정: RESEARCH_ONLY" in message
    assert "live 변경 금지" in message


def test_ascii_research_gate_report_removes_emoji_for_windows_console() -> None:
    # Given: a blocked assessment that would normally render with emoji.
    report = PaperReport(
        latest_run=None,
        open_positions=0,
        open_symbols=(),
        open_position_rows=(),
        trades=TradeReport(0, 0, 0, 0.0, 0.0, 0.0, 0.0),
        block_reasons=(),
        shadow_candidates=(),
        top_micro=(),
        latest_flip=None,
        top_adaptive=(),
        latest_news=(),
    )
    assessment = assess_paper_rotation(report, EvidenceProfile())

    # When: the assessment is formatted for a non-UTF-8 console.
    message = ascii_research_gate_report(assessment)

    # Then: the report remains readable without Unicode emoji code points.
    assert message.startswith("PAPER AUTO-RESEARCH GATE")
    assert "[FAIL] sample" in message
    assert "🧬" not in message


def candidate_report() -> PaperReport:
    return PaperReport(
        latest_run=PaperRunSummary(scanned=100, signals=18, opened=4, blocked=1, closed=3),
        open_positions=8,
        open_symbols=("A", "B", "C", "D", "E", "F", "G", "H"),
        open_position_rows=(),
        trades=TradeReport(140, 82, 58, 0.586, 880.0, 42.0, 1.86),
        block_reasons=(CountRow("entry_gate", 1),),
        shadow_candidates=(),
        top_micro=(),
        latest_flip=None,
        top_adaptive=(),
        latest_news=(),
    )


def write_promotion_bundle(root: Path, generated_at: datetime) -> Path:
    artifacts_dir = root / "artifacts"
    artifacts_dir.mkdir(parents=True)
    artifacts = {}
    for name in PROMOTION_ARTIFACTS:
        artifact_path = artifacts_dir / f"{name}.txt"
        _ = artifact_path.write_text(f"{name} evidence\n", encoding="utf-8")
        artifacts[name] = {
            "path": str(artifact_path),
            "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        }
    bundle_path = root / "promotion_bundle.json"
    payload = {
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "artifacts": artifacts,
        "metrics": {
            "wfa_positive_folds_ratio": 0.8,
            "out_of_sample_passed": True,
            "monte_carlo_passed": True,
            "cost_model_passed": True,
            "regime_passed": True,
            "capacity_passed": True,
            "pbo": 0.12,
            "deflated_sharpe_ratio": 0.97,
            "factor_exposure_passed": True,
        },
    }
    _ = bundle_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return bundle_path


def promotion_gate_detail(assessment: ResearchAssessment) -> str:
    gates = assessment.gates
    return "\n".join(gate.detail for gate in gates if gate.name == "promotion-bundle")

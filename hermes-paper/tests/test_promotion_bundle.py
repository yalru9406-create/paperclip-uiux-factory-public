from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from paper_engine.promotion_bundle import build_promotion_bundle, write_promotion_bundle
from paper_engine.promotion_bundle_sources import (
    PartialPromotionMetrics,
    PromotionDecisionInput,
    ValidationRow,
    ValidationRowsInput,
)
from paper_engine.research_promotion import evaluate_promotion_bundle
from paper_engine.research_promotion_schema import PromotionBundleDocument


def test_generator_complete_fixture_outputs_passing_bundle(tmp_path: Path) -> None:
    # Given: a fixture with every TAN validation artifact required for paper promotion.
    fixture = Path("tests/fixtures/promotion/complete")
    bundle_path = tmp_path / "promotion_bundle.json"
    summary_path = tmp_path / "promotion_summary.md"

    # When: the generator writes the JSON bundle and operator Markdown summary.
    result = write_promotion_bundle(fixture, bundle_path, summary_path)

    # Then: structured JSON marks a paper candidate awaiting C5, never live approval.
    payload = PromotionBundleDocument.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    assert result.promotion_bundle_status == "PASSING"
    assert payload.promotion_bundle_status == "PASSING"
    assert payload.paper_gate_verdict == "PAPER_ROTATION_CANDIDATE"
    assert payload.live_approval_state == "AWAITING_C5"
    assert payload.live_approval_state != "APPROVED"
    assert payload.discord_label == "PROMOTE_READY - C5 승인 대기"
    assert payload.blockers == ()
    assert payload.metrics.pbo == 0.12
    assert payload.artifacts.walk_forward.path.is_absolute()
    assert payload.artifacts.wfa_results.path.is_absolute()
    assert str(payload.artifacts.out_of_sample.path).endswith("tan_validation_comparison_latest.json")
    round_trip = evaluate_promotion_bundle(bundle_path, datetime(2026, 6, 20, 1, 0, tzinfo=UTC))
    assert round_trip.status == "PASSING"
    assert "PROMOTE_READY - C5 승인 대기" in summary_path.read_text(encoding="utf-8")


def test_generator_missing_oos_or_pbo_fails_closed() -> None:
    # Given: a fixture with WFA/MC evidence but no OOS or PBO artifact.
    fixture = Path("tests/fixtures/promotion/missing_oos_pbo")

    # When: the generator evaluates the incomplete evidence set.
    bundle = build_promotion_bundle(fixture)

    # Then: promotion fails closed with explicit blockers and research-only state.
    assert bundle.promotion_bundle_status == "FAIL"
    assert bundle.paper_gate_verdict == "RESEARCH_ONLY"
    assert bundle.live_approval_state == "NONE"
    assert "missing_artifact:out_of_sample" in bundle.blockers
    assert "missing_artifact:pbo" in bundle.blockers
    assert "missing_metric:out_of_sample_passed" in bundle.blockers
    assert "missing_metric:pbo" in bundle.blockers


def test_generator_output_is_deterministic(tmp_path: Path) -> None:
    # Given: one complete source fixture and two independent output targets.
    fixture = Path("tests/fixtures/promotion/complete")
    first_bundle_path = tmp_path / "first" / "promotion_bundle.json"
    first_summary_path = tmp_path / "first" / "promotion_summary.md"
    second_bundle_path = tmp_path / "second" / "promotion_bundle.json"
    second_summary_path = tmp_path / "second" / "promotion_summary.md"

    # When: the generator writes both outputs from the same source evidence.
    _ = write_promotion_bundle(fixture, first_bundle_path, first_summary_path)
    _ = write_promotion_bundle(fixture, second_bundle_path, second_summary_path)

    # Then: JSON and summary bytes are deterministic.
    assert first_bundle_path.read_bytes() == second_bundle_path.read_bytes()
    assert first_summary_path.read_bytes() == second_summary_path.read_bytes()


def test_generator_missing_required_hunter_source_fails_closed(tmp_path: Path) -> None:
    # Given: an otherwise complete fixture whose required hunter safety source is absent.
    fixture = copied_complete_fixture(tmp_path)
    hunter_path = fixture / "reports" / "tan_promotion_hunter_latest.json"
    hunter_path.unlink()

    # When: the generator evaluates the fixture.
    bundle = build_promotion_bundle(fixture)

    # Then: missing source evidence blocks promotion and never awaits C5.
    assert bundle.promotion_bundle_status == "FAIL"
    assert bundle.paper_gate_verdict == "RESEARCH_ONLY"
    assert bundle.live_approval_state == "NONE"
    assert "missing_source:tan_promotion_hunter_latest.json" in bundle.blockers


def test_generator_malformed_required_hunter_source_fails_closed(tmp_path: Path) -> None:
    # Given: an otherwise complete fixture whose required hunter safety source is malformed.
    fixture = copied_complete_fixture(tmp_path)
    hunter_path = fixture / "reports" / "tan_promotion_hunter_latest.json"
    _ = hunter_path.write_text("{not-json", encoding="utf-8")

    # When: the generator evaluates the fixture.
    bundle = build_promotion_bundle(fixture)

    # Then: malformed source evidence blocks promotion and never defaults to safe flags.
    assert bundle.promotion_bundle_status == "FAIL"
    assert bundle.paper_gate_verdict == "RESEARCH_ONLY"
    assert bundle.live_approval_state == "NONE"
    assert "malformed_source:tan_promotion_hunter_latest.json" in bundle.blockers


def test_generator_candidate_mismatch_rows_fail_closed(tmp_path: Path) -> None:
    # Given: selected candidate_a has no matching OOS/MC source rows, while candidate_b rows pass.
    fixture = copied_complete_fixture(tmp_path)
    validation_dir = fixture / "data" / "tan" / "validation"
    decision_path = validation_dir / "promotion_decision.json"
    decision = PromotionDecisionInput(
        candidate_id="candidate_a",
        generated_at_utc=datetime(2026, 6, 20, 0, 0, tzinfo=UTC),
        metrics=PartialPromotionMetrics(
            capacity_passed=True,
            cost_model_passed=True,
            deflated_sharpe_ratio=0.97,
            factor_exposure_passed=True,
            pbo=0.12,
            regime_passed=True,
            wfa_positive_folds_ratio=0.8,
        ),
    )
    _ = decision_path.write_text(decision.model_dump_json(exclude_none=True), encoding="utf-8")
    rewrite_rows_for_candidate(validation_dir / "tan_validation_comparison_latest.json", "candidate_b")
    rewrite_rows_for_candidate(validation_dir / "tan_candidate_evidence_bridge_latest.json", "candidate_b")

    # When: the generator evaluates the candidate-scoped evidence.
    bundle = build_promotion_bundle(fixture)

    # Then: validation rows from another candidate cannot be borrowed for promotion.
    assert bundle.candidate_id == "candidate_a"
    assert bundle.promotion_bundle_status == "FAIL"
    assert bundle.paper_gate_verdict == "RESEARCH_ONLY"
    assert bundle.live_approval_state == "NONE"
    assert "candidate_mismatch:tan_validation_comparison_latest.json" in bundle.blockers
    assert "candidate_mismatch:tan_candidate_evidence_bridge_latest.json" in bundle.blockers
    assert "missing_metric:out_of_sample_passed" in bundle.blockers
    assert "missing_metric:monte_carlo_passed" in bundle.blockers


def test_generator_missing_wfa_results_fails_closed(tmp_path: Path) -> None:
    # Given: the split manifest exists but the required WFA results artifact is absent.
    fixture = copied_complete_fixture(tmp_path)
    wfa_results_path = fixture / "data" / "tan" / "validation" / "wfa_results.parquet"
    wfa_results_path.unlink()

    # When: the generator evaluates the fixture.
    bundle = build_promotion_bundle(fixture)

    # Then: WFA is incomplete and cannot produce a passing promotion bundle.
    assert bundle.promotion_bundle_status == "FAIL"
    assert bundle.paper_gate_verdict == "RESEARCH_ONLY"
    assert bundle.live_approval_state == "NONE"
    assert "missing_artifact:wfa_results" in bundle.blockers


def copied_complete_fixture(tmp_path: Path) -> Path:
    source = Path("tests/fixtures/promotion/complete")
    target = tmp_path / "complete"
    _ = shutil.copytree(source, target)
    return target


def rewrite_rows_for_candidate(path: Path, candidate_id: str) -> None:
    payload = ValidationRowsInput.model_validate_json(path.read_text(encoding="utf-8"))
    rows = tuple(
        ValidationRow(
            candidate_id=candidate_id,
            evidence=row.evidence,
            monte_carlo_status=row.monte_carlo_status,
            oos_status=row.oos_status,
            regime_coverage_status=row.regime_coverage_status,
        )
        for row in payload.rows
    )
    rewritten = ValidationRowsInput(generated_at=payload.generated_at, rows=rows)
    _ = path.write_text(rewritten.model_dump_json(), encoding="utf-8")

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from paper_engine.freshness import PaperFreshness, build_paper_freshness, format_freshness_summary, utc_text
from paper_engine.reporting import PaperReport, TradeReport, build_report
from paper_engine.research_assessment import assess_paper_rotation
from paper_engine.research_types import EvidenceProfile, ResearchAssessment


@dataclass(frozen=True, slots=True)
class ArtifactTarget:
    filename: str
    count_rows: bool = False


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    filename: str
    exists: bool
    size_bytes: int | None
    rows: int | None
    mtime_utc: str | None


@dataclass(frozen=True, slots=True)
class StatusSafety:
    mode: str = "read-only"
    exchange_access: bool = False
    discord_send: bool = False
    secrets_read: bool = False
    report_write: bool = False
    position_mutation: bool = False
    live_mutation_allowed: bool = False
    live_mutation_performed: bool = False


@dataclass(frozen=True, slots=True)
class PaperStatus:
    engine: str
    status: str
    data_dir: str
    report: PaperReport
    safety: StatusSafety
    freshness: PaperFreshness
    promotion: ResearchAssessment
    artifacts: tuple[ArtifactMetadata, ...]
    issues: tuple[str, ...]


STATUS_ARTIFACTS: Final[tuple[ArtifactTarget, ...]] = (
    ArtifactTarget("paper_positions.json"),
    ArtifactTarget("paper_runs.jsonl", count_rows=True),
    ArtifactTarget("paper_trades.jsonl", count_rows=True),
    ArtifactTarget("paper_blocks.jsonl", count_rows=True),
    ArtifactTarget("paper_shadow.jsonl", count_rows=True),
    ArtifactTarget("paper_micro.jsonl", count_rows=True),
    ArtifactTarget("paper_flip.jsonl", count_rows=True),
    ArtifactTarget("paper_adaptive.jsonl", count_rows=True),
    ArtifactTarget("paper_news.jsonl", count_rows=True),
    ArtifactTarget("paper_report.json"),
    ArtifactTarget("paper_research_gate_latest.txt"),
    ArtifactTarget("paper_opportunity_latest.txt"),
    ArtifactTarget("paper_opportunity_state.json"),
)


def build_status(data_dir: Path) -> PaperStatus:
    report, issues = build_report_or_empty(data_dir)
    promotion = assess_paper_rotation(
        report,
        EvidenceProfile(),
        promotion_bundle_path=data_dir / "promotion_bundle.json",
    )
    status = "OK" if not issues else "DEGRADED"
    return PaperStatus(
        engine="paper",
        status=status,
        data_dir=str(data_dir),
        report=report,
        safety=StatusSafety(),
        freshness=build_paper_freshness(data_dir),
        promotion=promotion,
        artifacts=tuple(artifact_metadata(data_dir, target) for target in STATUS_ARTIFACTS),
        issues=tuple(issues),
    )


def build_report_or_empty(data_dir: Path) -> tuple[PaperReport, list[str]]:
    try:
        return build_report(data_dir), []
    except (OSError, ValueError, ValidationError) as exc:
        return empty_report(), [f"report_read_failed:{type(exc).__name__}"]


def empty_report() -> PaperReport:
    return PaperReport(
        latest_run=None,
        open_positions=0,
        open_symbols=(),
        open_position_rows=(),
        trades=TradeReport(
            closed=0,
            winners=0,
            losers=0,
            win_rate=0.0,
            total_pnl_quote=0.0,
            total_pnl_r=0.0,
            profit_factor=0.0,
        ),
        block_reasons=(),
        shadow_candidates=(),
        top_micro=(),
        latest_flip=None,
        top_adaptive=(),
        latest_news=(),
    )


def artifact_metadata(data_dir: Path, target: ArtifactTarget) -> ArtifactMetadata:
    path = data_dir / target.filename
    if not path.exists():
        return ArtifactMetadata(
            filename=target.filename,
            exists=False,
            size_bytes=None,
            rows=None,
            mtime_utc=None,
        )
    stat = path.stat()
    return ArtifactMetadata(
        filename=target.filename,
        exists=True,
        size_bytes=stat.st_size,
        rows=count_file_rows(path) if target.count_rows else None,
        mtime_utc=utc_text(stat.st_mtime),
    )


def count_file_rows(path: Path) -> int:
    try:
        with path.open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def format_status(status: PaperStatus) -> str:
    lines = [
        f"paper status | data={status.data_dir}",
        f"engine={status.engine} status={status.status}",
        summary_line(status.report),
        "safety: " + format_safety(status.safety),
        format_freshness_summary(status.freshness),
        "promotion: " + format_promotion(status.promotion),
        "block_reasons: " + format_block_reasons(status.report),
        "artifacts:",
    ]
    lines.extend(f"  {format_artifact(artifact)}" for artifact in status.artifacts)
    if status.issues:
        lines.append("issues: " + ", ".join(status.issues))
    return "\n".join(lines)


def summary_line(report: PaperReport) -> str:
    parts = [
        f"open_positions={report.open_positions}",
        f"closed_trades={report.trades.closed}",
        f"pnl_r={report.trades.total_pnl_r:.2f}",
    ]
    latest_run = report.latest_run
    if latest_run is None:
        parts.append("latest_run=missing")
    else:
        parts.append(
            "latest_run="
            + f"scanned:{latest_run.scanned},signals:{latest_run.signals},opened:{latest_run.opened},"
            + f"blocked:{latest_run.blocked},closed:{latest_run.closed}"
        )
    return "summary: " + " ".join(parts)


def format_safety(safety: StatusSafety) -> str:
    return " ".join(
        (
            f"mode={safety.mode}",
            f"exchange_access={bool_text(safety.exchange_access)}",
            f"discord_send={bool_text(safety.discord_send)}",
            f"secrets_read={bool_text(safety.secrets_read)}",
            f"report_write={bool_text(safety.report_write)}",
            f"position_mutation={bool_text(safety.position_mutation)}",
            f"live_mutation_allowed={bool_text(safety.live_mutation_allowed)}",
            f"live_mutation_performed={bool_text(safety.live_mutation_performed)}",
        )
    )


def format_promotion(promotion: ResearchAssessment) -> str:
    return " ".join(
        (
            f"paper_gate_verdict={promotion.paper_gate_verdict.value}",
            f"promotion_bundle_status={promotion.promotion_bundle_status.value}",
            f"live_approval_state={promotion.live_approval_state.value}",
            f"worst_status={promotion.worst_status.value}",
        )
    )


def format_block_reasons(report: PaperReport) -> str:
    if not report.block_reasons:
        return "none"
    return " ".join(f"{row.name}:{row.count}" for row in report.block_reasons[:8])


def format_artifact(artifact: ArtifactMetadata) -> str:
    parts = [artifact.filename, f"exists={bool_text(artifact.exists)}"]
    if artifact.size_bytes is not None:
        parts.append(f"bytes={artifact.size_bytes}")
    if artifact.rows is not None:
        parts.append(f"rows={artifact.rows}")
    if artifact.mtime_utc is not None:
        parts.append(f"mtime_utc={artifact.mtime_utc}")
    return " ".join(parts)


def bool_text(value: bool) -> str:
    return "true" if value else "false"

#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_config import JsonValue

PAPER_DATA_DIR: Final = Path("/srv/hermes-os/paper/data")
PAPER_ARTIFACT_NAMES: Final = (
    "paper_positions.json",
    "paper_runs.jsonl",
    "paper_trades.jsonl",
    "paper_blocks.jsonl",
    "paper_shadow.jsonl",
    "paper_micro.jsonl",
    "paper_flip.jsonl",
    "paper_adaptive.jsonl",
    "paper_news.jsonl",
    "paper_report.json",
    "paper_research_gate_latest.txt",
    "paper_opportunity_latest.txt",
    "paper_opportunity_state.json",
    "promotion_bundle.json",
)


@dataclass(frozen=True, slots=True)
class ArtifactStat:
    filename: str
    exists: bool
    size_bytes: int
    modified_at: str | None
    modified_epoch: float


def public_paper_payload(paper_data_dir: Path = PAPER_DATA_DIR) -> dict[str, JsonValue]:
    artifacts = paper_artifact_payload(paper_data_dir)
    promotion_gate = promotion_gate_payload(paper_data_dir)
    artifacts["promotionGate"] = promotion_gate
    return {
        "artifacts": artifacts,
        "promotionGate": promotion_gate,
        "freshness": freshness_payload(artifacts),
    }


def paper_artifact_payload(paper_data_dir: Path) -> dict[str, JsonValue]:
    base_payload: dict[str, JsonValue] = {
        "policy": "metadata_only",
        "artifactSet": "paper_latest_whitelist",
        "latestRunPresent": False,
        "artifactCount": 0,
        "totalBytes": 0,
        "newestModifiedAt": None,
        "artifacts": [],
        "expectedArtifacts": list(PAPER_ARTIFACT_NAMES),
        "rawContents": "not_exposed",
    }
    resolved_dir = safe_paper_data_dir(paper_data_dir)
    if resolved_dir is None:
        return base_payload
    stats = artifact_stats(resolved_dir, PAPER_ARTIFACT_NAMES)
    existing_stats = [item for item in stats if item.exists]
    return {
        **base_payload,
        "latestRunPresent": any(item.filename == "paper_runs.jsonl" and item.exists for item in stats),
        "artifactCount": len(existing_stats),
        "totalBytes": sum(item.size_bytes for item in existing_stats),
        "newestModifiedAt": newest_modified_at(existing_stats),
        "artifacts": [artifact_payload(item) for item in stats],
    }


def safe_paper_data_dir(paper_data_dir: Path) -> Path | None:
    try:
        resolved_dir = paper_data_dir.expanduser().resolve(strict=True)
    except OSError:
        return None
    if not resolved_dir.is_dir():
        return None
    return resolved_dir


def artifact_stats(artifact_dir: Path, filenames: tuple[str, ...]) -> list[ArtifactStat]:
    stats: list[ArtifactStat] = []
    for filename in filenames:
        entry = artifact_dir / filename
        if not entry.exists() or entry.is_symlink() or not entry.is_file():
            stats.append(
                ArtifactStat(
                    filename=filename,
                    exists=False,
                    size_bytes=0,
                    modified_at=None,
                    modified_epoch=0.0,
                ),
            )
            continue
        try:
            file_stat = entry.stat()
        except OSError:
            continue
        stats.append(
            ArtifactStat(
                filename=filename,
                exists=True,
                size_bytes=file_stat.st_size,
                modified_at=dt.datetime.fromtimestamp(file_stat.st_mtime, tz=dt.timezone.utc).isoformat(),
                modified_epoch=file_stat.st_mtime,
            ),
        )
    return stats


def newest_modified_at(stats: list[ArtifactStat]) -> str | None:
    if not stats:
        return None
    return max(stats, key=lambda item: item.modified_epoch).modified_at


def artifact_payload(stat: ArtifactStat) -> dict[str, JsonValue]:
    return {
        "name": stat.filename,
        "exists": stat.exists,
        "sizeBytes": stat.size_bytes,
        "modifiedAt": stat.modified_at,
    }


def promotion_gate_payload(paper_data_dir: Path) -> dict[str, JsonValue]:
    bundle_path = paper_data_dir / "promotion_bundle.json"
    if not bundle_path.is_file() or bundle_path.is_symlink():
        return promotion_gate_closed("MISSING", "promotion_bundle.json missing")
    try:
        raw = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return promotion_gate_closed("FAIL", "promotion_bundle.json unreadable")
    if not isinstance(raw, dict):
        return promotion_gate_closed("FAIL", "promotion_bundle.json must be an object")
    status = public_string(raw.get("promotion_bundle_status"), "FAIL")
    paper_gate = public_string(raw.get("paper_gate_verdict"), "RESEARCH_ONLY")
    live_approval = public_string(raw.get("live_approval_state"), "NONE")
    if live_approval == "APPROVED":
        live_approval = "NONE"
        status = "FAIL"
        paper_gate = "RESEARCH_ONLY"
    blockers = raw.get("blockers")
    blocker_items = [str(item) for item in blockers[:8]] if isinstance(blockers, list) else []
    return {
        "promotionBundleStatus": status,
        "paperGateVerdict": paper_gate,
        "liveApprovalState": live_approval,
        "discordLabel": public_string(raw.get("discord_label"), paper_gate),
        "blockers": blocker_items,
        "blockerCount": len(blockers) if isinstance(blockers, list) else 0,
        "rawContents": "not_exposed",
    }


def promotion_gate_closed(status: str, reason: str) -> dict[str, JsonValue]:
    return {
        "promotionBundleStatus": status,
        "paperGateVerdict": "RESEARCH_ONLY",
        "liveApprovalState": "NONE",
        "discordLabel": "RESEARCH_ONLY",
        "blockers": [reason],
        "blockerCount": 1,
        "rawContents": "not_exposed",
    }


def public_string(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def freshness_payload(paper_artifacts: dict[str, JsonValue]) -> dict[str, JsonValue]:
    artifacts = paper_artifacts.get("artifacts")
    rows = artifacts if isinstance(artifacts, list) else []
    return {
        "researchGate": freshness_item(rows, "paper_research_gate_latest.txt"),
        "opportunityLatest": freshness_item(rows, "paper_opportunity_latest.txt"),
        "promotionBundle": freshness_item(rows, "promotion_bundle.json"),
    }


def freshness_item(rows: list[JsonValue], name: str) -> dict[str, JsonValue]:
    for row in rows:
        if isinstance(row, dict) and row.get("name") == name:
            exists = row.get("exists") is True
            return {
                "name": name,
                "status": "PRESENT" if exists else "MISSING",
                "modifiedAt": row.get("modifiedAt") if isinstance(row.get("modifiedAt"), str) else None,
            }
    return {"name": name, "status": "MISSING", "modifiedAt": None}


def paper_warnings(paper_artifacts: dict[str, JsonValue], promotion_gate: dict[str, JsonValue]) -> list[JsonValue]:
    warnings: list[JsonValue] = []
    if promotion_gate.get("promotionBundleStatus") != "PASSING":
        warnings.append("promotion gate is not passing; live approval remains NONE")
    if paper_artifacts.get("latestRunPresent") is not True:
        warnings.append("paper latest run metadata missing")
    return warnings

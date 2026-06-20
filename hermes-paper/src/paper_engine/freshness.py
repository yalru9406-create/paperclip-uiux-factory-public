from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

RESEARCH_GATE_MAX_AGE_SECONDS: Final = 45 * 60


class FreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class FreshnessTarget:
    name: str
    path: Path
    max_age_seconds: int | None


@dataclass(frozen=True, slots=True)
class FileFreshness:
    name: str
    path: str
    status: FreshnessStatus
    age_seconds: int | None
    max_age_seconds: int | None
    mtime_utc: str | None


@dataclass(frozen=True, slots=True)
class PaperFreshness:
    generated_at_utc: str
    research_gate: FileFreshness
    opportunity_latest: FileFreshness


def build_paper_freshness(data_dir: Path, now_seconds: float | None = None) -> PaperFreshness:
    observed_seconds = time.time() if now_seconds is None else now_seconds
    return PaperFreshness(
        generated_at_utc=utc_text(observed_seconds),
        research_gate=file_freshness(
            FreshnessTarget(
                "research-gate",
                data_dir / "paper_research_gate_latest.txt",
                RESEARCH_GATE_MAX_AGE_SECONDS,
            ),
            observed_seconds,
        ),
        opportunity_latest=file_freshness(
            FreshnessTarget("opportunity-latest", data_dir / "paper_opportunity_latest.txt", None),
            observed_seconds,
        ),
    )


def file_freshness(target: FreshnessTarget, now_seconds: float) -> FileFreshness:
    path = target.path
    if not path.exists():
        return FileFreshness(target.name, str(path), FreshnessStatus.MISSING, None, target.max_age_seconds, None)
    mtime_seconds = path.stat().st_mtime
    age_seconds = max(0, int(now_seconds - mtime_seconds))
    status = FreshnessStatus.FRESH
    if target.max_age_seconds is not None and age_seconds > target.max_age_seconds:
        status = FreshnessStatus.STALE
    return FileFreshness(
        name=target.name,
        path=str(path),
        status=status,
        age_seconds=age_seconds,
        max_age_seconds=target.max_age_seconds,
        mtime_utc=utc_text(mtime_seconds),
    )


def format_freshness_summary(freshness: PaperFreshness) -> str:
    return "freshness: " + " | ".join(
        (
            freshness_item(freshness.research_gate),
            freshness_item(freshness.opportunity_latest),
        )
    )


def freshness_item(item: FileFreshness) -> str:
    parts = [f"{item.name}={item.status.value}"]
    if item.age_seconds is not None:
        parts.append(f"age={minutes_text(item.age_seconds)}")
    if item.max_age_seconds is not None:
        parts.append(f"max={minutes_text(item.max_age_seconds)}")
    return " ".join(parts)


def minutes_text(seconds: int) -> str:
    return f"{seconds // 60}m"


def utc_text(timestamp_seconds: float) -> str:
    return datetime.fromtimestamp(timestamp_seconds, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

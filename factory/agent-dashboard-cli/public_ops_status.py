#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from agent_config import JsonValue
from public_paper_status import PAPER_DATA_DIR, paper_warnings, public_paper_payload

TAN_SERVICE_WHITELIST: Final = (
    "tan-live",
    "tan-api",
    "tan-live-risk-manager",
    "tan-live-sentinel",
)
SERVICE_STATES: Final = frozenset(
    {
        "active",
        "inactive",
        "activating",
        "deactivating",
        "failed",
        "reloading",
        "maintenance",
        "unknown",
        "unavailable",
    },
)
SYSTEMCTL_TIMEOUT_SECONDS: Final = 2


@dataclass(frozen=True, slots=True)
class SystemctlResult:
    stdout: str
    returncode: int


class SystemctlRunner(Protocol):
    def __call__(self, service: str) -> SystemctlResult: ...


def public_ops_status_payload(
    paper_data_dir: Path = PAPER_DATA_DIR,
    runner: SystemctlRunner | None = None,
) -> dict[str, JsonValue]:
    active_runner = systemctl_is_active if runner is None else runner
    paper = public_paper_payload(paper_data_dir)
    paper_artifacts = require_dict(paper.get("artifacts"))
    promotion_gate = require_dict(paper.get("promotionGate"))
    return {
        "ok": True,
        "generatedAtUtc": utc_now(),
        "tanLive": tan_live_payload(active_runner),
        "paperArtifacts": paper_artifacts,
        "paper": paper,
        "discord": {
            "mode": "copy_only",
            "dangerousExecutionBridge": False,
            "developerPortalRequired": False,
        },
        "privateControls": {
            "enabled": False,
            "reason": "public host exposes read-only status only",
        },
        "safety": safety_payload(),
        "warnings": paper_warnings(paper_artifacts, promotion_gate),
        "vpsQa": vps_qa_payload(),
    }


def require_dict(value: JsonValue | None) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def tan_live_payload(runner: SystemctlRunner) -> dict[str, JsonValue]:
    return {
        "services": [service_payload(service, runner) for service in TAN_SERVICE_WHITELIST],
        "serviceProbe": "systemctl is-active whitelist only",
        "tanMutation": "not_performed",
        "liveMutationLock": (
            "Live mutation locked / C5: no live orders, positions, exchange configuration, "
            "service restart, or service mutation."
        ),
    }


def service_payload(service: str, runner: SystemctlRunner) -> dict[str, JsonValue]:
    result = runner(service)
    return {
        "name": service,
        "state": service_state(result),
        "source": "systemctl is-active",
    }


def systemctl_is_active(service: str) -> SystemctlResult:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            check=False,
            text=True,
            timeout=SYSTEMCTL_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return SystemctlResult(stdout="unavailable", returncode=127)
    except subprocess.TimeoutExpired:
        return SystemctlResult(stdout="unknown", returncode=124)
    return SystemctlResult(stdout=result.stdout, returncode=result.returncode)


def service_state(result: SystemctlResult) -> str:
    state = result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"
    return state if state in SERVICE_STATES else "unknown"


def safety_payload() -> dict[str, JsonValue]:
    return {
        "scope": "public_read_only",
        "liveMutationAllowed": False,
        "liveMutationPerformed": False,
        "tanMutation": "not_performed",
        "exchangeAccess": False,
        "secretsRead": False,
        "rawPaperContentsExposed": False,
    }


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def vps_qa_payload() -> dict[str, JsonValue]:
    return {
        "scope": "public_read_only",
        "privateTerminalEndpoints": "not_exposed_public",
        "safetyFacts": [
            "systemctl is-active whitelist only",
            "file metadata only for paper latest artifacts",
            "raw paper report contents not exposed",
            "private terminal and message controls hidden on public hosts",
            "live orders, positions, exchange configuration, and service mutation locked by C5",
        ],
    }

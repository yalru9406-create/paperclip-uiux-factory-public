from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_auto_research_wrapper_writes_latest_before_failed_discord(tmp_path: Path) -> None:
    # Given: a fake uv binary whose Discord send path fails after the dry-run report is generated.
    fake_uv = write_fake_uv(tmp_path)
    output_path = tmp_path / "paper_research_gate_latest.txt"
    record_path = tmp_path / "uv-calls.txt"

    # When: the research wrapper runs with Discord enabled.
    result = run_wrapper(
        "paper-auto-research.sh",
        {
            "FAKE_UV_FAIL_DISCORD": "1",
            "FAKE_UV_RECORD": wsl_path(record_path),
            "PAPER_DATA_DIR": wsl_path(tmp_path / "data"),
            "PAPER_RESEARCH_OUTPUT": wsl_path(output_path),
            "PAPER_SEND_DISCORD": "1",
            "PAPER_UV_BIN": fake_uv,
        },
    )

    # Then: the service result still reflects file-write success, not Discord success.
    assert result.returncode == 0, result.stderr
    latest = output_path.read_text(encoding="utf-8")
    calls = record_path.read_text(encoding="utf-8").splitlines()
    assert "generated_at_utc=" in latest
    assert "PAPER AUTO-RESEARCH GATE" in latest
    assert "research-gate" in calls[0]
    assert "--send-discord" not in calls[0]
    assert "--send-discord" in calls[1]
    assert "discord send failed after latest file was written" in result.stderr


def test_opportunity_wrapper_writes_latest_before_failed_discord(tmp_path: Path) -> None:
    # Given: a fake uv binary whose Discord send path fails after the dry-run report is generated.
    fake_uv = write_fake_uv(tmp_path)
    output_path = tmp_path / "paper_opportunity_latest.txt"
    record_path = tmp_path / "uv-calls.txt"

    # When: the opportunity wrapper runs with Discord enabled.
    result = run_wrapper(
        "paper-opportunity-monitor.sh",
        {
            "FAKE_UV_FAIL_DISCORD": "1",
            "FAKE_UV_RECORD": wsl_path(record_path),
            "PAPER_DATA_DIR": wsl_path(tmp_path / "data"),
            "PAPER_OPPORTUNITY_OUTPUT": wsl_path(output_path),
            "PAPER_SEND_DISCORD": "1",
            "PAPER_UV_BIN": fake_uv,
        },
    )

    # Then: the latest file is still published from the dry-run command.
    assert result.returncode == 0, result.stderr
    latest = output_path.read_text(encoding="utf-8")
    calls = record_path.read_text(encoding="utf-8").splitlines()
    assert "generated_at_utc=" in latest
    assert "PAPER OPPORTUNITY WATCH" in latest
    assert "opportunity-monitor" in calls[0]
    assert "--send-discord" not in calls[0]
    assert "--send-discord" in calls[1]


def test_wrappers_refuse_empty_or_missing_output_path() -> None:
    # Given: wrapper environments with no valid output destination.
    base_env = {
        "PAPER_DATA_DIR": "/tmp/paper-wrapper-test-data",
        "PAPER_SEND_DISCORD": "0",
        "PAPER_UV_BIN": "/bin/false",
    }

    # When: each wrapper is invoked with its required output path missing or empty.
    missing_research = run_wrapper("paper-auto-research.sh", base_env)
    empty_research = run_wrapper("paper-auto-research.sh", base_env | {"PAPER_RESEARCH_OUTPUT": ""})
    missing_opportunity = run_wrapper("paper-opportunity-monitor.sh", base_env)
    empty_opportunity = run_wrapper("paper-opportunity-monitor.sh", base_env | {"PAPER_OPPORTUNITY_OUTPUT": ""})

    # Then: none of them collapse to the historical `.tmp` target.
    assert missing_research.returncode != 0
    assert empty_research.returncode != 0
    assert missing_opportunity.returncode != 0
    assert empty_opportunity.returncode != 0
    assert "invalid output path" in missing_research.stderr
    assert ".tmp" not in missing_research.stderr


def test_wrapper_scripts_use_mktemp_trap_and_no_out_tmp_pattern() -> None:
    # Given: checked-in shell wrappers used by systemd.
    scripts = (
        REPO_ROOT / "scripts" / "paper-auto-research.sh",
        REPO_ROOT / "scripts" / "paper-opportunity-monitor.sh",
    )

    # When: the scripts are inspected.
    contents = "\n".join(path.read_text(encoding="utf-8") for path in scripts)

    # Then: temp-file discipline is explicit and cannot depend on systemd $out expansion.
    assert "mktemp" in contents
    assert "trap " in contents
    assert '"${out}.tmp"' not in contents
    assert '".tmp"' not in contents


def test_systemd_units_delegate_to_checked_in_scripts() -> None:
    # Given: checked-in systemd units for the two paper one-shot services.
    auto_unit = (REPO_ROOT / "systemd" / "paper-auto-research.service").read_text(encoding="utf-8")
    opportunity_unit = (REPO_ROOT / "systemd" / "paper-opportunity-monitor.service").read_text(encoding="utf-8")

    # When: their ExecStart lines are inspected.
    combined = auto_unit + "\n" + opportunity_unit

    # Then: systemd does not own shell variable expansion or temp-file construction.
    assert "ExecStart=/srv/hermes-os/paper/scripts/paper-auto-research.sh" in auto_unit
    assert "ExecStart=/srv/hermes-os/paper/scripts/paper-opportunity-monitor.sh" in opportunity_unit
    assert "/bin/bash -lc" not in combined
    assert "${out}" not in combined
    assert ".tmp" not in combined


def run_wrapper(script_name: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    assignments = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
    command = f"{assignments} bash {shlex.quote('scripts/' + script_name)}".strip()
    return subprocess.run(
        ["bash", "-lc", command],
        cwd=REPO_ROOT,
        env=merged_env,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )


def write_fake_uv(tmp_path: Path) -> str:
    fake_uv = tmp_path / "fake-uv"
    _ = fake_uv.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "${FAKE_UV_RECORD:?}"
if [[ "$*" == *"--send-discord"* && "${FAKE_UV_FAIL_DISCORD:-0}" == "1" ]]; then
  echo "discord failed" >&2
  exit 42
fi
if [[ "$*" == *"research-gate"* ]]; then
  echo "PAPER AUTO-RESEARCH GATE"
  echo "verdict: RESEARCH_ONLY"
elif [[ "$*" == *"opportunity-monitor"* ]]; then
  echo "PAPER OPPORTUNITY WATCH"
  echo "conditions: none"
else
  echo "unexpected command: $*" >&2
  exit 2
fi
""",
        encoding="utf-8",
        newline="\n",
    )
    fake_uv.chmod(0o755)
    return wsl_path(fake_uv)


def wsl_path(path: Path) -> str:
    result = subprocess.run(
        ["bash", "-lc", f"wslpath -a {shlex.quote(str(path))}"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return str(path)

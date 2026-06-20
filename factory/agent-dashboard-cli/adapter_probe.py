#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_config import DATA_DIR, JsonValue, command_preview, shell_word

MAX_PROBE_TEXT: Final = 4_000
SECRETISH_PATTERN: Final = re.compile(r"\b[A-Za-z0-9_-]{48,}\b")


@dataclass(frozen=True, slots=True)
class ProbeResult:
    ok: bool
    return_code: int
    duration_ms: int
    stdout: str
    stderr: str
    command: list[str]


def executable_path(name: str) -> str:
    probe = run_as_paperclip(["bash", "-lc", f"command -v {shell_word(name)}"], 10)
    if not probe.ok:
        return ""
    return probe.stdout.strip().splitlines()[0] if probe.stdout.strip() else ""


def command_evidence(name: str) -> dict[str, JsonValue]:
    path = executable_path(name)
    return {
        "name": name,
        "installed": bool(path),
        "path": path,
    }


def path_evidence(name: str, path: Path) -> dict[str, JsonValue]:
    exists = path.exists()
    return {
        "name": name,
        "exists": exists,
        "path": str(path),
        "sizeBytes": path.stat().st_size if exists else 0,
    }


def run_as_paperclip(command: list[str], timeout: int) -> ProbeResult:
    full_command = ["sudo", "-u", "paperclip", "env", f"HOME={DATA_DIR}", *command]
    started = time.monotonic()
    try:
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return ProbeResult(
            ok=False,
            return_code=124,
            duration_ms=duration_ms,
            stdout=sanitize_text(exc.stdout if isinstance(exc.stdout, str) else ""),
            stderr=sanitize_text(exc.stderr if isinstance(exc.stderr, str) else f"Timed out after {timeout}s."),
            command=command,
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    return ProbeResult(
        ok=result.returncode == 0,
        return_code=result.returncode,
        duration_ms=duration_ms,
        stdout=sanitize_text(result.stdout),
        stderr=sanitize_text(result.stderr),
        command=command,
    )


def probe_payload(probe: ProbeResult) -> dict[str, JsonValue]:
    return {
        "ok": probe.ok,
        "returnCode": probe.return_code,
        "durationMs": probe.duration_ms,
        "command": command_preview(probe.command),
        "stdout": probe.stdout,
        "stderr": probe.stderr,
    }


def sanitize_text(value: str) -> str:
    clipped = value[-MAX_PROBE_TEXT:]
    return SECRETISH_PATTERN.sub("<redacted>", clipped)

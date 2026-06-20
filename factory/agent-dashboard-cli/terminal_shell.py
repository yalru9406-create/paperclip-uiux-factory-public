#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Final, NewType

SessionName = NewType("SessionName", str)

MAX_INPUT_CHARS: Final = 8_192
CAPTURE_LINES: Final = 240
TMUX_SOCKET: Final = Path("/run/yalru-agent-cli-tmux.sock")

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


def session_name(agent_key: str) -> SessionName:
    safe_key = re.sub(r"[^A-Za-z0-9_-]+", "-", agent_key).strip("-")[:48]
    return SessionName(f"yalru-{safe_key or 'agent'}-cli")


def ensure_terminal(agent_key: str, cwd: Path, home: Path) -> dict[str, JsonValue]:
    session = session_name(agent_key)
    if not has_session(session, home):
        created = tmux(
            [
                "new-session",
                "-d",
                "-s",
                str(session),
                "-c",
                str(cwd),
                paperclip_shell_command(home, cwd, agent_key),
            ],
            home,
            timeout=10,
        )
        if not created["ok"]:
            return created
        time.sleep(0.15)
    return capture_terminal(agent_key, home)


def capture_terminal(agent_key: str, home: Path) -> dict[str, JsonValue]:
    session = session_name(agent_key)
    result = tmux(
        ["capture-pane", "-p", "-J", "-S", f"-{CAPTURE_LINES}", "-t", str(session)],
        home,
        timeout=10,
    )
    result["session"] = str(session)
    return result


def send_terminal_input(agent_key: str, cwd: Path, home: Path, text: str) -> dict[str, JsonValue]:
    if len(text) > MAX_INPUT_CHARS:
        return {
            "ok": False,
            "returnCode": 2,
            "durationMs": 0,
            "stdout": "",
            "stderr": f"Input exceeds {MAX_INPUT_CHARS} characters.",
            "session": str(session_name(agent_key)),
        }
    ready = ensure_terminal(agent_key, cwd, home)
    if not ready["ok"]:
        return ready
    session = session_name(agent_key)
    if text:
        sent = tmux(["send-keys", "-t", str(session), "-l", text], home, timeout=10)
        if not sent["ok"]:
            return sent
    entered = tmux(["send-keys", "-t", str(session), "Enter"], home, timeout=10)
    if not entered["ok"]:
        return entered
    time.sleep(0.25)
    return capture_terminal(agent_key, home)


def clear_terminal(agent_key: str, cwd: Path, home: Path) -> dict[str, JsonValue]:
    ready = ensure_terminal(agent_key, cwd, home)
    if not ready["ok"]:
        return ready
    session = session_name(agent_key)
    clear_scrollback = tmux(["clear-history", "-t", str(session)], home, timeout=10)
    if not clear_scrollback["ok"]:
        return clear_scrollback
    tmux(["send-keys", "-t", str(session), "C-l"], home, timeout=10)
    time.sleep(0.1)
    return capture_terminal(agent_key, home)


def restart_terminal(agent_key: str, cwd: Path, home: Path) -> dict[str, JsonValue]:
    session = session_name(agent_key)
    if has_session(session, home):
        stopped = tmux(["kill-session", "-t", str(session)], home, timeout=10)
        if not stopped["ok"]:
            return stopped
    return ensure_terminal(agent_key, cwd, home)


def has_session(session: SessionName, home: Path) -> bool:
    result = tmux(["has-session", "-t", str(session)], home, timeout=5)
    return bool(result["ok"])


def tmux(args: list[str], home: Path, timeout: int) -> dict[str, JsonValue]:
    started = time.monotonic()
    command = ["tmux", "-S", str(TMUX_SOCKET), *args]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "ok": result.returncode == 0,
        "returnCode": result.returncode,
        "durationMs": duration_ms,
        "stdout": result.stdout[-20_000:],
        "stderr": result.stderr[-12_000:],
        "command": command_preview(command),
    }


def command_preview(command: list[str]) -> str:
    return " ".join(shell_word(part) for part in command)


def paperclip_shell_command(home: Path, cwd: Path, agent_key: str) -> str:
    standby = f"/usr/local/bin/yalru-agent-standby {shell_word(agent_key)}"
    return f"sudo -u paperclip env HOME={shell_word(str(home))} SHELL=/bin/bash TERM=xterm-256color {standby}"


def shell_word(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=@+-]+", value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"

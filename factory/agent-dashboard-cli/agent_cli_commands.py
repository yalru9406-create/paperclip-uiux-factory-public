#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Final

from agent_config import (
    CONFIG_PATH,
    DATA_DIR,
    ROOT,
    AgentConfig,
    JsonValue,
    command_preview,
    read_json_file,
    string_field,
)

FACTORY_BIN: Final = Path("/usr/local/bin/yalru-uiux-factory")
PAPERCLIP_BIN: Final = Path("/usr/bin/paperclipai")
MAX_MESSAGE_BYTES: Final = 16_384
COMMAND_TIMEOUT_SECONDS: Final = 180


def command_json(command: list[str], timeout: int = COMMAND_TIMEOUT_SECONDS) -> dict[str, JsonValue]:
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=ROOT,
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
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-12000:],
        "command": command_preview(command),
    }


def parse_request_body(handler: BaseHTTPRequestHandler) -> dict[str, JsonValue]:
    length_header = handler.headers.get("Content-Length", "0")
    try:
        length = int(length_header)
    except ValueError as exc:
        raise RuntimeError("Invalid Content-Length") from exc
    if length > MAX_MESSAGE_BYTES:
        raise RuntimeError("Request body is too large")
    raw = handler.rfile.read(length)
    decoded = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(decoded, dict):
        raise RuntimeError("Request JSON must be an object")
    return decoded


def chat_command(agent: AgentConfig, message: str, wake: bool) -> list[str]:
    command = [str(FACTORY_BIN), str(agent.key), "--message", message]
    if not wake:
        command.append("--no-wake")
    return command


def agent_status_command(agent: AgentConfig) -> list[str]:
    config = read_json_file(CONFIG_PATH)
    api_base = string_field(config, "apiBase")
    return [
        "sudo",
        "-u",
        "paperclip",
        f"HOME={DATA_DIR}",
        str(PAPERCLIP_BIN),
        "agent",
        "get",
        agent.id,
        "--api-base",
        api_base,
        "--json",
    ]


def request_token(handler: BaseHTTPRequestHandler) -> str:
    authorization = handler.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return handler.headers.get("X-Yalru-Agent-Token", "").strip()

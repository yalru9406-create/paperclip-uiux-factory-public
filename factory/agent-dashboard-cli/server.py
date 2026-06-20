#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from typing import Callable, Final
from urllib.parse import parse_qs, urlsplit

from adapter_auth import adapter_status_payload, reconnect_input
from discord_surfaces import discord_surfaces_payload
from agent_config import (
    CONFIG_PATH,
    DATA_DIR,
    ROOT,
    AgentConfig,
    JsonValue,
    agent_payload,
    command_preview,
    read_json_file,
    resolve_agent,
    room_state,
    string_field,
)
from terminal_shell import capture_terminal, clear_terminal, ensure_terminal, restart_terminal, send_terminal_input

SCRIPT_PATH: Final = ROOT / "agent-dashboard-cli" / "agent-dashboard-cli.js"
FACTORY_BIN: Final = Path("/usr/local/bin/yalru-uiux-factory")
PAPERCLIP_BIN: Final = Path("/usr/bin/paperclipai")
MAX_MESSAGE_BYTES: Final = 16_384
COMMAND_TIMEOUT_SECONDS: Final = 180
AUTH_TOKEN_ENV: Final = "YALRU_AGENT_CLI_TOKEN"


TerminalAction = Callable[[AgentConfig, dict[str, JsonValue]], dict[str, JsonValue]]


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



class AgentCliHandler(BaseHTTPRequestHandler):
    server_version = "YalruAgentCli/1.0"

    def log_message(self, format_value: str, *args: str) -> None:
        return

    def do_GET(self) -> None:
        match self.path.split("?", 1)[0]:
            case "/health":
                self.write_json({"ok": True})
            case "/agent-dashboard-cli.js":
                self.write_script()
            case "/api/context":
                self.write_context()
            case "/api/status":
                self.write_status()
            case "/api/adapter/status":
                self.write_adapter_status()
            case "/api/terminal/output":
                self.write_terminal_output()
            case _:
                self.write_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        match self.path.split("?", 1)[0]:
            case "/api/chat":
                self.write_chat()
            case "/api/terminal/start":
                self.write_terminal_start()
            case "/api/terminal/input":
                self.write_terminal_input()
            case "/api/terminal/clear":
                self.write_terminal_clear()
            case "/api/terminal/restart":
                self.write_terminal_restart()
            case "/api/adapter/reconnect":
                self.write_adapter_reconnect()
            case _:
                self.write_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)

    def write_script(self) -> None:
        body = SCRIPT_PATH.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_context(self) -> None:
        agent = self.resolve_agent_from_query()
        if agent is None:
            self.write_json({"ok": False, "error": "Unknown agent"}, HTTPStatus.NOT_FOUND)
            return
        self.write_json(
            {
                "ok": True,
                "agent": agent_payload(agent),
                "room": room_state(),
                "discordSurfaces": discord_surfaces_payload(),
                "commands": {
                    "attach": command_preview(chat_command(agent, "<message>", False)),
                    "wake": command_preview(chat_command(agent, "<message>", True)),
                },
            },
        )

    def write_status(self) -> None:
        if not self.require_private_access():
            return
        agent = self.resolve_agent_from_query()
        if agent is None:
            self.write_json({"ok": False, "error": "Unknown agent"}, HTTPStatus.NOT_FOUND)
            return
        result = command_json(agent_status_command(agent), 30)
        result["agent"] = agent_payload(agent)
        self.write_json(result, HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_GATEWAY)

    def write_adapter_status(self) -> None:
        if not self.require_private_access():
            return
        agent = self.resolve_agent_from_query()
        if agent is None:
            self.write_json({"ok": False, "error": "Unknown agent"}, HTTPStatus.NOT_FOUND)
            return
        self.write_json({"ok": True, "agent": agent_payload(agent), "adapter": adapter_status_payload(agent)})

    def write_chat(self) -> None:
        if not self.require_private_access():
            return
        try:
            payload = parse_request_body(self)
            route_value = string_field(payload, "agentRoute")
            message = string_field(payload, "message").strip()
            wake = payload.get("wake") is True
            agent = resolve_agent(route_value)
            if agent is None:
                self.write_json({"ok": False, "error": "Unknown agent"}, HTTPStatus.NOT_FOUND)
                return
            if not message:
                self.write_json({"ok": False, "error": "Message is required"}, HTTPStatus.BAD_REQUEST)
                return
            result = command_json(chat_command(agent, message, wake))
            result["agent"] = agent_payload(agent)
            self.write_json(result, HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_GATEWAY)
        except (json.JSONDecodeError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.write_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def write_terminal_output(self) -> None:
        if not self.require_private_access():
            return
        agent = self.resolve_agent_from_query()
        if agent is None:
            self.write_json({"ok": False, "error": "Unknown agent"}, HTTPStatus.NOT_FOUND)
            return
        self.write_terminal_result(agent, capture_terminal(str(agent.key), DATA_DIR))

    def write_terminal_start(self) -> None:
        if not self.require_private_access():
            return
        self.write_terminal_payload_result(lambda agent, _: ensure_terminal(str(agent.key), ROOT, DATA_DIR))

    def write_terminal_input(self) -> None:
        if not self.require_private_access():
            return
        self.write_terminal_payload_result(
            lambda agent, payload: send_terminal_input(str(agent.key), ROOT, DATA_DIR, string_field(payload, "input")),
        )

    def write_terminal_clear(self) -> None:
        if not self.require_private_access():
            return
        self.write_terminal_payload_result(lambda agent, _: clear_terminal(str(agent.key), ROOT, DATA_DIR))

    def write_terminal_restart(self) -> None:
        if not self.require_private_access():
            return
        self.write_terminal_payload_result(lambda agent, _: restart_terminal(str(agent.key), ROOT, DATA_DIR))

    def write_adapter_reconnect(self) -> None:
        if not self.require_private_access():
            return
        try:
            payload = parse_request_body(self)
            agent = resolve_agent(string_field(payload, "agentRoute"))
            if agent is None:
                self.write_json({"ok": False, "error": "Unknown agent"}, HTTPStatus.NOT_FOUND)
                return
            command = reconnect_input(agent)
            result = send_terminal_input(str(agent.key), ROOT, DATA_DIR, command)
            result["agent"] = agent_payload(agent)
            result["adapterReconnectCommand"] = command
            self.write_json(result, HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_GATEWAY)
        except (json.JSONDecodeError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.write_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def write_terminal_payload_result(self, action: TerminalAction) -> None:
        try:
            payload = parse_request_body(self)
            agent = resolve_agent(string_field(payload, "agentRoute"))
            if agent is None:
                self.write_json({"ok": False, "error": "Unknown agent"}, HTTPStatus.NOT_FOUND)
                return
            self.write_terminal_result(agent, action(agent, payload))
        except (json.JSONDecodeError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.write_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def write_terminal_result(self, agent: AgentConfig, result: dict[str, JsonValue]) -> None:
        result["agent"] = agent_payload(agent)
        self.write_json(result, HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_GATEWAY)

    def resolve_agent_from_query(self) -> AgentConfig | None:
        values = parse_qs(urlsplit(self.path).query)
        route_value = values.get("agentRoute", [""])[0]
        return resolve_agent(route_value)

    def require_private_access(self) -> bool:
        if self.is_loopback_request() or self.has_valid_token():
            return True
        self.write_json({"ok": False, "error": "Private endpoint requires local access or token"}, HTTPStatus.FORBIDDEN)
        return False

    def is_loopback_request(self) -> bool:
        if self.headers.get("X-Yalru-Internal-Proxy", ""):
            return False
        candidate = str(self.client_address[0])
        try:
            return ip_address(candidate).is_loopback
        except ValueError:
            return False

    def has_valid_token(self) -> bool:
        expected = os.environ.get(AUTH_TOKEN_ENV, "").strip()
        return bool(expected) and request_token(self) == expected

    def write_json(self, payload: dict[str, JsonValue], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def main() -> int:  # noqa: BROAD_EXCEPT_OK
    server = ThreadingHTTPServer(("127.0.0.1", 4192), AgentCliHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

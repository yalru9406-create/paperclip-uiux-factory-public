#!/usr/bin/env python3
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Final, Literal

from agent_config import AgentConfig, DATA_DIR, JsonValue, command_preview, shell_word
from adapter_probe import command_evidence, executable_path, path_evidence, probe_payload, run_as_paperclip

AdapterState = Literal[
    "authenticated",
    "available",
    "connect_required",
    "not_applicable",
    "not_installed",
    "unsupported",
    "error",
]

ANTIGRAVITY_HOME: Final = DATA_DIR / ".gemini" / "antigravity-cli"
ANTIGRAVITY_AGENTAPI: Final = ANTIGRAVITY_HOME / "bin" / "agentapi"
ANTIGRAVITY_TOKEN: Final = ANTIGRAVITY_HOME / "antigravity-oauth-token"
ANTIGRAVITY_AGY: Final = DATA_DIR / ".local" / "bin" / "agy"
FREECLAUDE_CONFIG: Final = DATA_DIR / ".freeclaude.json"
FREECLAUDE_UPSTREAM: Final = Path("/usr/bin/freeclaude")


def adapter_status_payload(agent: AgentConfig) -> dict[str, JsonValue]:
    match agent.adapter:
        case "codex_local":
            return codex_status(agent)
        case "antigravity_local":
            return antigravity_status(agent)
        case "hermes_local":
            return hermes_status(agent)
        case _:
            return base_status(
                agent,
                "Unknown adapter",
                "not_applicable",
                "No status probe is configured for this adapter.",
                "",
                [],
            )


def reconnect_input(agent: AgentConfig) -> str:
    match agent.adapter:
        case "codex_local":
            return "codex login --device-auth"
        case "antigravity_local":
            return (
                "antigravity models || printf '%s\\n' "
                + shell_word(
                    "Antigravity CLI is installed as agy/antigravity. agentapi mode is optional and still needs ANTIGRAVITY_LS_ADDRESS."
                )
            )
        case "hermes_local":
            return (
                "printf '%s\\n' "
                + shell_word(
                    "This GLM lane is served by its configured local CLI wrapper. It is not an OAuth CLI session; "
                    "do not paste paid API keys into this terminal."
                )
            )
        case _:
            return "printf '%s\\n' 'No reconnect command is configured for this adapter.'"


def codex_status(agent: AgentConfig) -> dict[str, JsonValue]:
    command_path = executable_path("codex")
    if not command_path:
        return base_status(agent, "Codex ChatGPT OAuth", "not_installed", "codex is not on PATH.", "", [])

    probe = run_as_paperclip(["codex", "login", "status"], 20)
    combined = f"{probe.stdout}\n{probe.stderr}"
    if probe.ok and "Logged in using ChatGPT" in combined:
        return base_status(
            agent,
            "Codex ChatGPT OAuth",
            "authenticated",
            "Logged in using ChatGPT subscription auth.",
            "codex login --device-auth",
            [probe_payload(probe)],
        )
    return base_status(
        agent,
        "Codex ChatGPT OAuth",
        "connect_required",
        "Codex is installed, but ChatGPT login status did not pass.",
        "codex login --device-auth",
        [probe_payload(probe)],
    )


def antigravity_status(agent: AgentConfig) -> dict[str, JsonValue]:
    evidence = [
        path_evidence("agy", ANTIGRAVITY_AGY),
        path_evidence("agentapi", ANTIGRAVITY_AGENTAPI),
        path_evidence("oauthToken", ANTIGRAVITY_TOKEN),
    ]
    if not ANTIGRAVITY_AGY.exists() and not ANTIGRAVITY_AGENTAPI.exists():
        return base_status(
            agent,
            "Gemini Antigravity",
            "not_installed",
            "Antigravity agy/agentapi is not installed on the VPS.",
            reconnect_input(agent),
            evidence,
        )
    if not ANTIGRAVITY_TOKEN.exists():
        return base_status(
            agent,
            "Gemini Antigravity",
            "connect_required",
            "Antigravity agentapi exists, but the OAuth token file is missing.",
            reconnect_input(agent),
            evidence,
        )

    ls_address = os.environ.get("ANTIGRAVITY_LS_ADDRESS", "")
    if ls_address:
        return base_status(
            agent,
            "Gemini Antigravity",
            "available",
            "Antigravity token exists and ANTIGRAVITY_LS_ADDRESS is set for this service process.",
            "",
            evidence,
        )
    if ANTIGRAVITY_AGY.exists():
        probe = run_as_paperclip([str(ANTIGRAVITY_AGY), "models"], 30)
        evidence.append(probe_payload(probe))
        if probe.ok:
            return base_status(
                agent,
                "Gemini Antigravity",
                "authenticated",
                "Antigravity agy CLI is installed, token exists, and the models probe succeeded.",
                "",
                evidence,
            )
    return base_status(
        agent,
        "Gemini Antigravity",
        "available",
        "Antigravity token exists; agy CLI standby is configured, while agentapi remains optional until ANTIGRAVITY_LS_ADDRESS is set.",
        reconnect_input(agent),
        evidence,
    )


def hermes_status(agent: AgentConfig) -> dict[str, JsonValue]:
    match str(agent.key):
        case "gajecode":
            evidence = [command_evidence("gajecode"), command_evidence("gjc"), command_evidence("hermes")]
            if executable_path("gajecode") and executable_path("gjc") and executable_path("hermes"):
                return base_status(
                    agent, "GajeCode GLM 5.2 wrapper", "available",
                    "gajecode is installed and launches upstream gjc with the YALRU GLM 5.2 env when available.",
                    reconnect_input(agent), evidence,
                )
        case "freeclaude":
            evidence = [
                command_evidence("freeclaude"),
                path_evidence("freeclaudeUpstream", FREECLAUDE_UPSTREAM),
                path_evidence("freeclaudeConfig", FREECLAUDE_CONFIG),
                command_evidence("hermes"),
            ]
            if executable_path("freeclaude") and FREECLAUDE_UPSTREAM.exists() and executable_path("hermes"):
                return base_status(
                    agent, "FreeClaude GLM 5.2 wrapper", "available",
                    "freeclaude is installed and launches upstream FreeClaude with the YALRU GLM 5.2 env when available.",
                    reconnect_input(agent), evidence,
                )
        case _:
            evidence = [command_evidence("hermes"), path_evidence("freeclaudeConfig", FREECLAUDE_CONFIG), command_evidence("freeclaude")]
            if executable_path("hermes"):
                return base_status(
                    agent, "Hermes GLM 5.2 local wrapper", "available",
                    "Hermes CLI is installed and is the active GLM lane for this agent.",
                    reconnect_input(agent), evidence,
                )
    evidence = [command_evidence("hermes"), command_evidence("gajecode"), command_evidence("gjc"), command_evidence("freeclaude"), path_evidence("freeclaudeConfig", FREECLAUDE_CONFIG)]
    if not executable_path("freeclaude"):
        return base_status(
            agent, "Hermes/FreeClaude local wrapper", "not_installed",
            "Neither hermes nor freeclaude is on PATH.", "", evidence,
        )
    if FREECLAUDE_CONFIG.exists():
        state: AdapterState = "available"
        summary = "FreeClaude wrapper is installed and has a config file; OAuth is not used for this lane."
    else:
        state = "connect_required"
        summary = "FreeClaude wrapper is installed, but no ~/.freeclaude.json config exists for the paperclip user."
    return base_status(agent, "Hermes/FreeClaude local wrapper", state, summary, reconnect_input(agent), evidence)


def gemini_cli_status(agent: AgentConfig) -> dict[str, JsonValue]:
    command_path = executable_path("gemini")
    if not command_path:
        return {
            "agent": {
                "key": str(agent.key),
                "adapter": "gemini_cli",
            },
            "provider": "Gemini CLI",
            "state": "not_installed",
            "summary": "gemini is not on PATH.",
            "reconnectCommand": "gemini",
            "checkedAtUnix": int(time.time()),
            "evidence": [],
            "replacedBy": "Gemini Antigravity",
        }

    probe = run_as_paperclip(["gemini", "--list-extensions"], 30)
    combined = f"{probe.stdout}\n{probe.stderr}"
    if "IneligibleTierError" in combined or "UNSUPPORTED_CLIENT" in combined or "no longer supported" in combined:
        state: AdapterState = "unsupported"
        summary = "Installed Gemini CLI reports this client is no longer supported for individual Code Assist; use Antigravity."
    elif "Manual authorization is required" in combined or "Error authenticating" in combined:
        state = "connect_required"
        summary = "Gemini CLI is installed but needs an interactive OAuth login."
    elif probe.ok:
        state = "authenticated"
        summary = "Gemini CLI auth probe completed successfully."
    else:
        state = "error"
        summary = "Gemini CLI auth probe failed."
    payload = {
        "agent": {
            "key": str(agent.key),
            "adapter": "gemini_cli",
        },
        "provider": "Gemini CLI",
        "state": state,
        "summary": summary,
        "reconnectCommand": "gemini",
        "checkedAtUnix": int(time.time()),
        "evidence": [probe_payload(probe)],
    }
    payload["replacedBy"] = "Gemini Antigravity"
    return payload


def base_status(
    agent: AgentConfig,
    provider: str,
    state: AdapterState,
    summary: str,
    reconnect_command: str,
    evidence: list[JsonValue],
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "agent": {
            "key": str(agent.key),
            "adapter": agent.adapter,
        },
        "provider": provider,
        "state": state,
        "summary": summary,
        "reconnectCommand": reconnect_command,
        "checkedAtUnix": int(time.time()),
        "evidence": evidence,
    }
    if agent.adapter == "antigravity_local":
        payload["geminiCli"] = gemini_cli_status(agent)
    return payload

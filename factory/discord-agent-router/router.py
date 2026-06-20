#!/usr/bin/env python3
"""Safe deterministic Discord-to-agent intake router.

This module does not call Discord or execute agents. It normalizes a Discord
message envelope into the Yalru OS/Paperclip intake shape while preserving
source references and keeping dangerousExecutionBridge disabled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY = ROOT / "agents.yaml"


class RouterError(ValueError):
    """Expected routing/validation error."""


def load_registry(path: Path = DEFAULT_REGISTRY) -> Dict[str, Any]:
    # agents.yaml is intentionally JSON-shaped YAML so stdlib json is enough.
    data = json.loads(path.read_text(encoding="utf-8"))
    agents = data.get("agents")
    if not isinstance(agents, list):
        raise RouterError("registry missing agents list")
    seen = set()
    for agent in agents:
        route = agent.get("routeKey")
        if not route or route in seen:
            raise RouterError(f"invalid or duplicate routeKey: {route!r}")
        seen.add(route)
        if agent.get("dangerousExecutionBridge") is not False:
            raise RouterError(f"agent {route} must set dangerousExecutionBridge=false")
    return data


def agent_by_route(registry: Dict[str, Any], route_key: str) -> Dict[str, Any]:
    for agent in registry["agents"]:
        if agent["routeKey"] == route_key:
            return agent
    raise RouterError(f"unknown agent route: {route_key}")


def payload_hash(message: str, discord_message_id: str) -> str:
    h = hashlib.sha256()
    h.update(discord_message_id.encode("utf-8"))
    h.update(b"\0")
    h.update(message.encode("utf-8"))
    return h.hexdigest()


def normalize_envelope(envelope: Dict[str, Any], registry: Dict[str, Any] | None = None) -> Dict[str, Any]:
    registry = registry or load_registry()
    route_key = str(envelope.get("agentRoute") or "").strip()
    message = str(envelope.get("message") or "").strip()
    discord_thread_id = str(envelope.get("discordThreadId") or "").strip()
    discord_message_id = str(envelope.get("discordMessageId") or "").strip()
    author_id = str(envelope.get("authorId") or "").strip()

    missing = [
        name
        for name, value in {
            "agentRoute": route_key,
            "message": message,
            "discordThreadId": discord_thread_id,
            "discordMessageId": discord_message_id,
            "authorId": author_id,
        }.items()
        if not value
    ]
    if missing:
        raise RouterError("missing required field(s): " + ", ".join(missing))

    agent = agent_by_route(registry, route_key)
    status = agent["status"]
    execution_status = "queued" if status.startswith("degraded_") else "ready"

    return {
        "schemaVersion": 1,
        "source": "discord",
        "sourceRef": f"discord:{discord_thread_id}:{discord_message_id}",
        "payloadHash": payload_hash(message, discord_message_id),
        "dangerousExecutionBridge": False,
        "agentRoute": route_key,
        "agentName": agent["agentName"],
        "adapterType": agent["adapterType"],
        "displayName": agent["displayName"],
        "discordThreadId": discord_thread_id,
        "discordMessageId": discord_message_id,
        "authorIdHash": hashlib.sha256(author_id.encode("utf-8")).hexdigest()[:16],
        "message": message,
        "executionStatus": execution_status,
        "laneStatus": status,
        "degradedReason": agent["fallbackPolicy"] if execution_status == "queued" else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize Discord agent message envelope")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--input", "-i", help="JSON envelope file; defaults to stdin")
    args = parser.parse_args()
    raw = Path(args.input).read_text(encoding="utf-8") if args.input else __import__("sys").stdin.read()
    envelope = json.loads(raw)
    out = normalize_envelope(envelope, load_registry(Path(args.registry)))
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

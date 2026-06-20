#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from agent_config import ROOT, JsonValue, string_field

DISCORD_ROUTER_REGISTRY: Final = ROOT / "discord-agent-router" / "agents.yaml"
DISCORD_ROUTE_ORDER: Final = ("orchestrator", "lazycodex", "freeclaude-glm", "gajecode", "antigravity")
DEFAULT_SURFACE_STATE: Final = "planned channel/thread"


def discord_surfaces_payload(registry_path: Path = DISCORD_ROUTER_REGISTRY) -> list[dict[str, JsonValue]]:
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, dict):
        return []

    raw_agents = raw.get("agents")
    raw_surfaces = raw.get("recommendedDiscordSurfaces")
    if not isinstance(raw_agents, list) or not isinstance(raw_surfaces, list):
        return []

    agents_by_route: dict[str, dict[str, str]] = {}
    for raw_agent in raw_agents:
        if not isinstance(raw_agent, dict):
            continue
        route_key = string_field(raw_agent, "routeKey")
        if route_key not in DISCORD_ROUTE_ORDER:
            continue
        agents_by_route[route_key] = {
            "displayName": string_field(raw_agent, "displayName"),
            "agentName": string_field(raw_agent, "agentName"),
            "status": string_field(raw_agent, "status") or "unknown",
            "channelId": string_field(raw_agent, "discordChannelId"),
        }

    surfaces_by_route: dict[str, dict[str, str]] = {}
    for raw_surface in raw_surfaces:
        if not isinstance(raw_surface, dict):
            continue
        route_key = string_field(raw_surface, "routeKey")
        if route_key not in DISCORD_ROUTE_ORDER:
            continue
        surfaces_by_route[route_key] = {
            "name": string_field(raw_surface, "name"),
            "channelId": string_field(raw_surface, "channelId"),
            "purpose": string_field(raw_surface, "purpose"),
            "surfaceState": string_field(raw_surface, "surfaceState") or DEFAULT_SURFACE_STATE,
        }

    surfaces: list[dict[str, JsonValue]] = []
    for route_key in DISCORD_ROUTE_ORDER:
        agent = agents_by_route.get(route_key)
        surface = surfaces_by_route.get(route_key)
        if agent is None or surface is None:
            continue
        name = surface["name"]
        channel = f"#{name}" if name else DEFAULT_SURFACE_STATE
        channel_id = surface["channelId"] or agent["channelId"]
        if surface["channelId"] and agent["channelId"] and surface["channelId"] != agent["channelId"]:
            continue
        surfaces.append(
            {
                "routeKey": route_key,
                "displayName": agent["displayName"] or route_key,
                "agentName": agent["agentName"],
                "name": name,
                "channel": channel,
                "channelId": channel_id,
                "status": agent["status"],
                "purpose": surface["purpose"],
                "surfaceState": surface["surfaceState"],
                "dangerousExecutionBridge": False,
            },
        )
    return surfaces

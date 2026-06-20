#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NewType

FactoryRoot = NewType("FactoryRoot", Path)
AgentKey = NewType("AgentKey", str)

def default_root() -> Path:
    override = os.environ.get("YALRU_FACTORY_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


ROOT: Final = FactoryRoot(default_root())
CONFIG_PATH: Final = ROOT / "config" / "agents.json"
STATE_PATH: Final = ROOT / "rooms" / "state.json"
DATA_DIR: Final = Path(os.environ.get("YALRU_DATA_DIR", str(Path(ROOT).parent))).expanduser()

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class AgentConfig:
    key: AgentKey
    id: str
    name: str
    adapter: str
    role: str
    route_key: str


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "agent"


def read_json_file(path: Path) -> dict[str, JsonValue]:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path} did not contain a JSON object")
    return raw


def string_field(data: dict[str, JsonValue], key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else ""


def load_agents() -> dict[AgentKey, AgentConfig]:
    data = read_json_file(CONFIG_PATH)
    raw_agents = data.get("agents")
    if not isinstance(raw_agents, dict):
        raise RuntimeError("agents.json is missing agents")

    agents: dict[AgentKey, AgentConfig] = {}
    for raw_key, raw_value in raw_agents.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, dict):
            continue
        key = AgentKey(raw_key)
        name = string_field(raw_value, "name")
        agents[key] = AgentConfig(
            key=key,
            id=string_field(raw_value, "id"),
            name=name,
            adapter=string_field(raw_value, "adapter"),
            role=string_field(raw_value, "role"),
            route_key=slugify(name),
        )
    return agents


def resolve_agent(route_value: str) -> AgentConfig | None:
    normalized = slugify(route_value)
    for agent in load_agents().values():
        if normalized in {str(agent.key), agent.id, agent.route_key}:
            return agent
    return None


def room_state() -> dict[str, JsonValue]:
    if not STATE_PATH.exists():
        return {}
    return read_json_file(STATE_PATH)


def agent_payload(agent: AgentConfig) -> dict[str, JsonValue]:
    return {
        "key": str(agent.key),
        "id": agent.id,
        "name": agent.name,
        "adapter": agent.adapter,
        "role": agent.role,
        "routeKey": agent.route_key,
    }


def command_preview(command: list[str]) -> str:
    return " ".join(shell_word(part) for part in command)


def shell_word(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=@+-]+", value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"

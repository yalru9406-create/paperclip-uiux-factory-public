#!/usr/bin/env python3
"""Build sanitized Yalru OS intake dry-run payloads from router output.

The helper reads normalized output from router.py and writes an intake-shaped JSON
artifact. It never reads secrets, calls the network, or enables live execution.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final, TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

INTAKE_TYPE: Final = "discord_agent_router_dry_run"


class IntakeError(Exception):
    """Expected dry-run intake conversion error."""


def _json_object(value: JsonValue) -> JsonObject:
    if isinstance(value, dict):
        return value
    raise IntakeError("expected normalized router output object")


def _required_string(data: JsonObject, key: str) -> str:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise IntakeError(f"missing required string field: {key}")


def _required_false(data: JsonObject, key: str) -> bool:
    if data.get(key) is False:
        return False
    raise IntakeError(f"{key} must be false for dry-run intake")


def build_intake_payload(normalized: JsonObject) -> JsonObject:
    """Return a sanitized dry-run intake payload from normalized router output."""
    bridge_enabled = _required_false(normalized, "dangerousExecutionBridge")
    agent_route = _required_string(normalized, "agentRoute")
    execution_status = _required_string(normalized, "executionStatus")
    lane_status = _required_string(normalized, "laneStatus")

    return {
        "schemaVersion": 1,
        "intakeType": INTAKE_TYPE,
        "source": _required_string(normalized, "source"),
        "sourceRef": _required_string(normalized, "sourceRef"),
        "payloadHash": _required_string(normalized, "payloadHash"),
        "dangerousExecutionBridge": bridge_enabled,
        "agentRoute": agent_route,
        "agentName": _required_string(normalized, "agentName"),
        "adapterType": _required_string(normalized, "adapterType"),
        "displayName": _required_string(normalized, "displayName"),
        "executionStatus": execution_status,
        "laneStatus": lane_status,
        "dispatch": {
            "mode": "dry_run",
            "liveNetworkCalls": False,
            "serviceMutation": False,
        },
        "body": {
            "message": _required_string(normalized, "message"),
            "discordThreadId": _required_string(normalized, "discordThreadId"),
            "discordMessageId": _required_string(normalized, "discordMessageId"),
            "authorIdHash": _required_string(normalized, "authorIdHash"),
        },
    }


def read_json_object(path: str | None) -> JsonObject:
    """Read a JSON object from a file path or stdin."""
    raw = Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()
    return _json_object(json.loads(raw))


def write_payload(payload: JsonObject, path: str | None) -> None:
    """Write or print the sanitized dry-run payload."""
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")
        return
    print(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build safe Yalru OS intake dry-run JSON")
    parser.add_argument("--input", "-i", help="normalized router JSON file; defaults to stdin")
    parser.add_argument("--output", "-o", help="write sanitized intake JSON to this path")
    parser.add_argument("--summary", action="store_true", help="print one-line dry-run summary")
    args = parser.parse_args()

    try:
        payload = build_intake_payload(read_json_object(args.input))
    except IntakeError as exc:
        parser.error(str(exc))

    write_payload(payload, args.output)
    if args.summary:
        print(
            "dry-run intake "
            f"route={payload['agentRoute']} "
            f"status={payload['executionStatus']} "
            "dangerousExecutionBridge=false "
            f"output={args.output or 'stdout'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from server import discord_surfaces_payload


REQUIRED_ROUTES = {"lazycodex", "freeclaude-glm", "gajecode", "antigravity"}


def assert_discord_surfaces_contract() -> None:
    surfaces = discord_surfaces_payload()
    routes = {str(surface.get("routeKey", "")) for surface in surfaces}
    missing_routes = REQUIRED_ROUTES - routes
    assert not missing_routes, f"missing Discord routes: {sorted(missing_routes)}"

    by_route = {str(surface["routeKey"]): surface for surface in surfaces}
    for route_key in REQUIRED_ROUTES:
        surface = by_route[route_key]
        for field in ("routeKey", "displayName", "name", "status", "purpose"):
            value = surface.get(field)
            assert isinstance(value, str) and value, f"{route_key}.{field} missing"
        assert surface.get("dangerousExecutionBridge") is False, f"{route_key} bridge must be disabled"

    assert "degraded" in str(by_route["freeclaude-glm"]["status"]), "FreeClaude GLM lane must show degraded status"
    assert "degraded" in str(by_route["gajecode"]["status"]), "GajeCode GLM lane must show degraded status"


def assert_malformed_registry_is_safe() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        missing = Path(tmp_dir) / "missing-agents.yaml"
        malformed = Path(tmp_dir) / "agents.yaml"
        malformed.write_text("{bad json", encoding="utf-8")
        assert discord_surfaces_payload(missing) == []
        assert discord_surfaces_payload(malformed) == []


def main() -> int:
    assert_discord_surfaces_contract()
    assert_malformed_registry_is_safe()
    print(json.dumps({"ok": True, "routes": sorted(REQUIRED_ROUTES)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
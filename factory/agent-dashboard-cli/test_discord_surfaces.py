#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from server import discord_surfaces_payload


EXPECTED_CHANNEL_IDS = {
    "orchestrator": "1517790192516206632",
    "lazycodex": "1517790167090594002",
    "freeclaude-glm": "1517790172756840468",
    "gajecode": "1517790179606138961",
    "antigravity": "1517790186191458376",
}
REQUIRED_ROUTES = set(EXPECTED_CHANNEL_IDS)


class DiscordSurfacesTests(unittest.TestCase):
    def test_surfaces_include_verified_agent_channels(self) -> None:
        surfaces = discord_surfaces_payload()
        routes = {str(surface.get("routeKey", "")) for surface in surfaces}
        missing_routes = REQUIRED_ROUTES - routes
        self.assertFalse(missing_routes, f"missing Discord routes: {sorted(missing_routes)}")

        by_route = {str(surface["routeKey"]): surface for surface in surfaces}
        for route_key in REQUIRED_ROUTES:
            surface = by_route[route_key]
            for field in ("routeKey", "displayName", "name", "status", "purpose"):
                value = surface.get(field)
                self.assertIsInstance(value, str, f"{route_key}.{field} missing")
                self.assertTrue(value, f"{route_key}.{field} missing")
            self.assertEqual(surface.get("channelId"), EXPECTED_CHANNEL_IDS[route_key])
            self.assertEqual(surface.get("surfaceState"), "created_channel_verified")
            self.assertEqual(surface.get("channel"), f"#{surface['name']}")
            self.assertIs(surface.get("dangerousExecutionBridge"), False)

        self.assertIn("degraded", str(by_route["freeclaude-glm"]["status"]))
        self.assertIn("degraded", str(by_route["gajecode"]["status"]))

    def test_malformed_registry_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing-agents.yaml"
            malformed = Path(tmp_dir) / "agents.yaml"
            malformed.write_text("{bad json", encoding="utf-8")
            self.assertEqual(discord_surfaces_payload(missing), [])
            self.assertEqual(discord_surfaces_payload(malformed), [])

    def test_channel_id_mismatch_drops_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = Path(tmp_dir) / "agents.yaml"
            registry.write_text(
                json.dumps(
                    {
                        "agents": [
                            {
                                "routeKey": "lazycodex",
                                "displayName": "LazyCodex Bot",
                                "agentName": "LazyCodex GPT Lane",
                                "status": "ready",
                                "discordChannelId": "expected-channel",
                            },
                        ],
                        "recommendedDiscordSurfaces": [
                            {
                                "routeKey": "lazycodex",
                                "name": "agent-lazycodex",
                                "channelId": "wrong-channel",
                                "surfaceState": "created_channel_verified",
                                "purpose": "bounded Codex/LazyCodex work",
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )
            self.assertEqual(discord_surfaces_payload(registry), [])


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DiscordSurfacesTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        return 1
    print(json.dumps({"ok": True, "routes": sorted(REQUIRED_ROUTES)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

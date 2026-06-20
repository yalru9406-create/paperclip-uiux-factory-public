import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class HermesConfigPlanDocsTests(unittest.TestCase):
    def test_plan_documents_dispatch_modes_restart_rollback_and_safety_boundaries(self):
        # Given: the router documentation set.
        plan_path = ROOT / "hermes-config-plan.md"

        # When: the Hermes gateway plan is inspected.
        text = plan_path.read_text(encoding="utf-8")

        # Then: it covers the non-secret operational contract.
        required = [
            "one-dispatcher mode",
            "optional multi-token mode",
            "DISCORD_AGENT_ROUTER_REGISTRY",
            "DISCORD_AGENT_ROUTER_DEFAULT_BRIDGE_ENABLED=false",
            "backup",
            "validate",
            "restart hermes-gateway",
            "rollback",
            "C4",
            "C5",
            "Do not print, echo, log, capture, or commit Discord bot tokens",
        ]
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()

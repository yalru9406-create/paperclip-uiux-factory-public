import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import intake_client
import router


class IntakeClientTests(unittest.TestCase):
    def envelope(self, route="lazycodex", message="run safe QA"):
        return {
            "agentRoute": route,
            "message": message,
            "discordThreadId": "1517721645811499099",
            "discordMessageId": "1234567890",
            "authorId": "user-42",
        }

    def test_builds_dry_run_intake_payload_when_router_output_is_normalized(self):
        # Given: a normalized safe router payload.
        normalized = router.normalize_envelope(self.envelope())

        # When: the payload is converted for Yalru OS intake dry-run use.
        out = intake_client.build_intake_payload(normalized)

        # Then: the observable intake contract is preserved without live execution.
        self.assertEqual(out["intakeType"], "discord_agent_router_dry_run")
        self.assertEqual(out["sourceRef"], normalized["sourceRef"])
        self.assertEqual(out["payloadHash"], normalized["payloadHash"])
        self.assertFalse(out["dangerousExecutionBridge"])
        self.assertFalse(out["dispatch"]["liveNetworkCalls"])
        self.assertFalse(out["dispatch"]["serviceMutation"])
        self.assertNotIn("authorId", out)

    def test_preserves_glm_queued_status_when_lane_is_degraded(self):
        # Given: a degraded GLM lane normalized by the router.
        normalized = router.normalize_envelope(self.envelope("freeclaude-glm"))

        # When: the dry-run intake payload is built.
        out = intake_client.build_intake_payload(normalized)

        # Then: the queued/degraded status remains explicit and safe.
        self.assertEqual(out["agentRoute"], "freeclaude-glm")
        self.assertEqual(out["executionStatus"], "queued")
        self.assertIn("quota", out["laneStatus"])
        self.assertFalse(out["dangerousExecutionBridge"])

    def test_cli_writes_sanitized_payload_when_output_path_is_provided(self):
        # Given: a normalized router output written to a temp input file.
        normalized = router.normalize_envelope(self.envelope("lazycodex"))
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "normalized.json"
            output_path = tmp_path / "intake.json"
            input_path.write_text(json.dumps(normalized), encoding="utf-8")

            # When: the CLI runs in dry-run mode.
            result = subprocess.run(
                [
                    sys.executable,
                    "discord-agent-router/intake_client.py",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--summary",
                ],
                check=True,
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
            )

            # Then: summary stdout and JSON artifact are sanitized.
            self.assertIn("route=lazycodex", result.stdout)
            text = output_path.read_text(encoding="utf-8")
            self.assertIn('"dangerousExecutionBridge": false', text)
            self.assertNotIn("user-42", text)


if __name__ == "__main__":
    unittest.main()

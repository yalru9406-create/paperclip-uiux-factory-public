import json
import unittest

import router


class RouterTests(unittest.TestCase):
    def envelope(self, route="lazycodex", message="run safe QA"):
        return {
            "agentRoute": route,
            "message": message,
            "discordThreadId": "1517721645811499099",
            "discordMessageId": "1234567890",
            "authorId": "user-42",
        }

    def test_ready_lane_normalizes_source_ref_and_disables_bridge(self):
        out = router.normalize_envelope(self.envelope())
        self.assertEqual(out["agentRoute"], "lazycodex")
        self.assertEqual(out["executionStatus"], "ready")
        self.assertEqual(out["sourceRef"], "discord:1517721645811499099:1234567890")
        self.assertFalse(out["dangerousExecutionBridge"])
        self.assertEqual(len(out["payloadHash"]), 64)
        self.assertNotIn("user-42", json.dumps(out))

    def test_glm_lane_queues_when_quota_degraded(self):
        out = router.normalize_envelope(self.envelope("freeclaude-glm"))
        self.assertEqual(out["executionStatus"], "queued")
        self.assertIn("quota", out["laneStatus"])
        self.assertIn("GLM", out["degradedReason"])
        self.assertFalse(out["dangerousExecutionBridge"])

    def test_gajecode_lane_queues_when_quota_degraded(self):
        out = router.normalize_envelope(self.envelope("gajecode"))
        self.assertEqual(out["executionStatus"], "queued")
        self.assertIn("quota", out["laneStatus"])

    def test_unknown_route_rejected(self):
        with self.assertRaises(router.RouterError):
            router.normalize_envelope(self.envelope("unknown-agent"))

    def test_malformed_payload_rejected(self):
        bad = self.envelope()
        bad["message"] = "   "
        with self.assertRaises(router.RouterError):
            router.normalize_envelope(bad)


if __name__ == "__main__":
    unittest.main()

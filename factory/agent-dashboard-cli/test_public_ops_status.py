#!/usr/bin/env python3
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import server
from agent_config import JsonValue
from public_ops_status import SystemctlResult, public_ops_status_payload
from public_paper_status import paper_artifact_payload


class FakeContextHandler:
    def __init__(self) -> None:
        self.payload: dict[str, JsonValue] | None = None
        self.status: HTTPStatus | None = None

    def resolve_agent_from_query(self) -> str:
        return "hermes"

    def write_json(self, payload: dict[str, JsonValue], status: HTTPStatus = HTTPStatus.OK) -> None:
        self.payload = payload
        self.status = status


def agent_payload(_: str) -> dict[str, JsonValue]:
    return {
        "key": "hermes-top-orchestrator",
        "id": "YAL-hermes",
        "name": "Hermes",
        "adapter": "hermes_local",
        "role": "orchestrator",
        "routeKey": "hermes",
    }


def test_context_includes_public_ops_status_when_public_controls_are_hidden() -> None:
    # Given: the public context endpoint resolves a dashboard agent.
    handler = FakeContextHandler()
    original_agent_payload = server.agent_payload
    original_room_state = server.room_state
    original_discord_surfaces_payload = server.discord_surfaces_payload
    original_public_ops_status_payload = server.public_ops_status_payload
    server.agent_payload = agent_payload
    server.room_state = lambda: {"identifier": "YAL-public"}
    server.discord_surfaces_payload = lambda: []
    server.public_ops_status_payload = lambda: public_ops_status_payload(
        paper_data_dir=Path(__file__).parent,
        runner=lambda _: SystemctlResult(stdout="active\n", returncode=0),
    )

    try:
        # When: the context payload is written.
        server.AgentCliHandler.write_context(handler)
    finally:
        server.agent_payload = original_agent_payload
        server.room_state = original_room_state
        server.discord_surfaces_payload = original_discord_surfaces_payload
        server.public_ops_status_payload = original_public_ops_status_payload

    # Then: public-safe ops status is present without requiring private endpoints.
    assert handler.status == HTTPStatus.OK
    assert handler.payload is not None
    ops_status = handler.payload.get("opsStatus")
    assert isinstance(ops_status, dict), "expected /api/context to expose public opsStatus"
    tan_live = ops_status.get("tanLive")
    assert isinstance(tan_live, dict)
    assert tan_live.get("tanMutation") == "not_performed"
    assert "C5" in str(tan_live.get("liveMutationLock", ""))
    paper_artifacts = ops_status.get("paperArtifacts")
    assert isinstance(paper_artifacts, dict)
    assert paper_artifacts.get("policy") == "metadata_only"
    vps_qa = ops_status.get("vpsQa")
    assert isinstance(vps_qa, dict)
    assert vps_qa.get("privateTerminalEndpoints") == "not_exposed_public"


def test_public_status_endpoint_exposes_safe_contract() -> None:
    # Given: the public status endpoint is requested without private access.
    handler = FakeContextHandler()
    original_public_ops_status_payload = server.public_ops_status_payload
    server.public_ops_status_payload = lambda: public_ops_status_payload(
        paper_data_dir=Path(__file__).parent,
        runner=lambda _: SystemctlResult(stdout="active\n", returncode=0),
    )

    try:
        # When: the endpoint payload is written.
        server.AgentCliHandler.write_public_status(handler)
    finally:
        server.public_ops_status_payload = original_public_ops_status_payload

    # Then: the response is a public-safe contract, not private command state.
    assert handler.status == HTTPStatus.OK
    assert handler.payload is not None
    assert handler.payload.get("ok") is True
    private_controls = handler.payload.get("privateControls")
    assert isinstance(private_controls, dict)
    assert private_controls.get("enabled") is False
    safety = handler.payload.get("safety")
    assert isinstance(safety, dict)
    assert safety.get("liveMutationAllowed") is False
    assert safety.get("liveMutationPerformed") is False
    paper = handler.payload.get("paper")
    assert isinstance(paper, dict)
    promotion_gate = paper.get("promotionGate")
    assert isinstance(promotion_gate, dict)
    assert promotion_gate.get("liveApprovalState") == "NONE"
    assert "commands" not in str(handler.payload)


def test_paper_artifact_payload_reads_only_whitelisted_metadata(tmp_path: Path) -> None:
    # Given: real PAPER data artifacts plus an unrelated file that must not leak through public JSON.
    (tmp_path / "paper_runs.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "paper_report.json").write_text('{"secretish":"raw report body"}', encoding="utf-8")
    (tmp_path / "paper_research_gate_latest.txt").write_text("gate body must stay server-side", encoding="utf-8")
    (tmp_path / "private_notes.txt").write_text("not public", encoding="utf-8")

    # When: the public payload summarizes the data directory.
    payload = paper_artifact_payload(tmp_path)

    # Then: it exposes only existence, size, and mtime for expected files.
    assert payload["policy"] == "metadata_only"
    assert payload["rawContents"] == "not_exposed"
    assert payload["latestRunPresent"] is True
    assert payload["artifactCount"] == 3
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, list)
    artifact_names = {str(item["name"]) for item in artifacts if isinstance(item, dict) and item.get("exists")}
    assert artifact_names == {"paper_runs.jsonl", "paper_report.json", "paper_research_gate_latest.txt"}
    assert "private_notes.txt" not in str(payload)
    assert "raw report body" not in str(payload)
    assert str(tmp_path) not in str(payload)
    assert "dataDir" not in payload


def main() -> int:
    test_context_includes_public_ops_status_when_public_controls_are_hidden()
    test_public_status_endpoint_exposes_safe_contract()
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temp_dir:
        test_paper_artifact_payload_reads_only_whitelisted_metadata(Path(temp_dir))
    print('{"ok": true, "publicOpsStatus": true}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

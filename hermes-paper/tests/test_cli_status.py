from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from typer.testing import CliRunner

from paper_engine.cli import app
from paper_engine.ledger import PaperLedger
from paper_engine.models import ClosedPaperTrade, PaperBlock, PaperPosition, PaperRunSummary, SignalSide


def test_status_cli_reports_safety_state_without_writing_report(tmp_path: Path) -> None:
    # Given: a paper data directory with current state artifacts but no generated report file.
    ledger = PaperLedger(tmp_path)
    position = PaperPosition(
        "paper",
        "BTCUSDT",
        SignalSide.SHORT,
        10,
        100.0,
        2.0,
        104.0,
        92.0,
        "BTC:10:SHORT",
    )
    trade = ClosedPaperTrade(
        "paper",
        "ETHUSDT",
        SignalSide.LONG,
        1,
        2,
        50.0,
        55.0,
        48.0,
        56.0,
        5.0,
        1.25,
        "TAKE_PROFIT",
        "ETH:1:LONG",
    )
    ledger.save_positions([position])
    ledger.append_jsonl(ledger.trades_path, trade)

    # When: the read-only status command inspects the directory.
    result = CliRunner().invoke(app, ["status", "--data-dir", str(tmp_path)])

    # Then: it reports artifact metadata and explicit safety state without creating report output.
    assert result.exit_code == 0, result.output
    assert "paper status" in result.output
    assert "open_positions=1" in result.output
    assert "closed_trades=1" in result.output
    assert "paper_positions.json exists=true" in result.output
    assert "paper_trades.jsonl exists=true" in result.output
    assert "mode=read-only" in result.output
    assert "exchange_access=false" in result.output
    assert "discord_send=false" in result.output
    assert "secrets_read=false" in result.output
    assert "report_write=false" in result.output
    assert "position_mutation=false" in result.output
    assert "live_mutation_allowed=false" in result.output
    assert "live_approval_state=NONE" in result.output
    assert not (tmp_path / "paper_report.json").exists()


def test_status_cli_json_reports_promotion_and_block_state_without_writing(tmp_path: Path) -> None:
    ledger = PaperLedger(tmp_path)
    ledger.append_run(PaperRunSummary(scanned=10, signals=2, opened=0, blocked=2))
    ledger.append_jsonl(
        ledger.blocks_path,
        PaperBlock(
            "paper",
            "BTC:10:SHORT",
            "BTCUSDT",
            SignalSide.SHORT,
            "entry_gate",
            ("trend filter",),
        ),
    )

    result = CliRunner().invoke(app, ["status", "--data-dir", str(tmp_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = cast(dict[str, object], json.loads(result.output))
    summary = cast(dict[str, object], payload["summary"])
    latest_run = cast(dict[str, object], summary["latestRun"])
    promotion_gate = cast(dict[str, object], payload["promotionGate"])
    safety = cast(dict[str, object], payload["safety"])
    assert payload["engine"] == "paper"
    assert payload["status"] == "OK"
    assert latest_run["blocked"] == 2
    assert payload["blockReasons"] == [{"name": "entry_gate", "count": 1}]
    assert promotion_gate["paperGateVerdict"] == "RESEARCH_ONLY"
    assert promotion_gate["promotionBundleStatus"] == "MISSING"
    assert promotion_gate["liveApprovalState"] == "NONE"
    assert safety["liveMutationAllowed"] is False
    assert safety["liveMutationPerformed"] is False
    assert safety["reportWrite"] is False
    assert not (tmp_path / "paper_report.json").exists()


def test_status_cli_json_fails_closed_for_malformed_positions(tmp_path: Path) -> None:
    _ = (tmp_path / "paper_positions.json").write_text("{not-json", encoding="utf-8")

    result = CliRunner().invoke(app, ["status", "--data-dir", str(tmp_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = cast(dict[str, object], json.loads(result.output))
    summary = cast(dict[str, object], payload["summary"])
    promotion_gate = cast(dict[str, object], payload["promotionGate"])
    safety = cast(dict[str, object], payload["safety"])
    assert payload["status"] == "DEGRADED"
    assert summary["openPositions"] == 0
    assert promotion_gate["paperGateVerdict"] == "RESEARCH_ONLY"
    assert promotion_gate["liveApprovalState"] == "NONE"
    assert safety["liveMutationAllowed"] is False
    assert payload["issues"] == ["report_read_failed:ValidationError"]
    assert not (tmp_path / "paper_report.json").exists()

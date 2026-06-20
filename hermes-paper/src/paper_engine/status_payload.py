from __future__ import annotations

from dataclasses import asdict

from paper_engine.status import PaperStatus


def status_payload(status: PaperStatus) -> dict[str, object]:
    latest_run = status.report.latest_run
    return {
        "engine": status.engine,
        "status": status.status,
        "dataDir": status.data_dir,
        "generatedAtUtc": status.freshness.generated_at_utc,
        "summary": {
            "openPositions": status.report.open_positions,
            "openSymbols": list(status.report.open_symbols),
            "closedTrades": status.report.trades.closed,
            "pnlR": status.report.trades.total_pnl_r,
            "latestRun": asdict(latest_run) if latest_run is not None else None,
        },
        "blockReasons": [asdict(row) for row in status.report.block_reasons],
        "freshness": {
            "researchGate": asdict(status.freshness.research_gate),
            "opportunityLatest": asdict(status.freshness.opportunity_latest),
        },
        "promotionGate": {
            "paperGateVerdict": status.promotion.paper_gate_verdict.value,
            "promotionBundleStatus": status.promotion.promotion_bundle_status.value,
            "liveApprovalState": status.promotion.live_approval_state.value,
            "discordLabel": status.promotion.discord_label,
            "worstStatus": status.promotion.worst_status.value,
            "gates": [asdict(gate) for gate in status.promotion.gates],
        },
        "safety": {
            "mode": status.safety.mode,
            "exchangeAccess": status.safety.exchange_access,
            "discordSend": status.safety.discord_send,
            "secretsRead": status.safety.secrets_read,
            "reportWrite": status.safety.report_write,
            "positionMutation": status.safety.position_mutation,
            "liveMutationAllowed": status.safety.live_mutation_allowed,
            "liveMutationPerformed": status.safety.live_mutation_performed,
        },
        "artifacts": [asdict(artifact) for artifact in status.artifacts],
        "issues": list(status.issues),
    }

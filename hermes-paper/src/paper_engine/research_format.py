from __future__ import annotations

from typing import Final

from paper_engine.research_types import GateStatus, ResearchAssessment

STATUS_ICON: Final[dict[GateStatus, str]] = {
    GateStatus.PASS: "✅",
    GateStatus.WARN: "⚠️",
    GateStatus.FAIL: "⛔",
}


def format_research_gate_report(assessment: ResearchAssessment) -> str:
    lines = [
        "🧬 PAPER AUTO-RESEARCH GATE",
        f"판정: {assessment.verdict}",
        f"paper_gate_verdict: {assessment.paper_gate_verdict.value}",
        f"promotion_bundle_status: {assessment.promotion_bundle_status.value}",
        f"live_approval_state: {assessment.live_approval_state.value}",
        f"discord_label: {assessment.discord_label}",
        f"후보 방향: {assessment.primary_direction}",
        "━━━━━━━━━━━━━━━",
    ]
    for gate in assessment.gates:
        icon = STATUS_ICON[gate.status]
        lines.append(f"{icon} {gate.name}: {gate.status.value}")
        lines.append(f"근거: {gate.detail}")
        lines.append(f"다음: {gate.action}")
    return "\n".join(lines)


def ascii_research_gate_report(assessment: ResearchAssessment) -> str:
    lines = [
        "PAPER AUTO-RESEARCH GATE",
        f"verdict: {assessment.verdict}",
        f"paper_gate_verdict: {assessment.paper_gate_verdict.value}",
        f"promotion_bundle_status: {assessment.promotion_bundle_status.value}",
        f"live_approval_state: {assessment.live_approval_state.value}",
        f"discord_label: {ascii_safe_text(assessment.discord_label)}",
        f"candidate: {assessment.primary_direction}",
        "---------------",
    ]
    for gate in assessment.gates:
        lines.append(f"[{gate.status.value}] {gate.name}")
        lines.append(f"detail: {ascii_safe_text(gate.detail)}")
        lines.append(f"next: {ascii_safe_text(gate.action)}")
    return "\n".join(lines)


def ascii_safe_text(value: str) -> str:
    replacements: Final[dict[str, str]] = {
        "∞": "INF",
        "변경 금지": "change forbidden",
    }
    text = value
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text.encode("ascii", errors="replace").decode("ascii")

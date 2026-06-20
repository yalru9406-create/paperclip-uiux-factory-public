from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Annotated

import anyio
import httpx2
import typer
from rich.console import Console

from paper_engine.discord import (
    DiscordConfigError,
    preview_paper_discord_report,
    send_paper_discord_report,
    send_paper_discord_text,
)
from paper_engine.freshness import build_paper_freshness
from paper_engine.ledger import PaperLedger
from paper_engine.news import parse_news_event_json
from paper_engine.opportunity import (
    OpportunityAlertState,
    OpportunityMonitorConfig,
    OpportunityMonitorInput,
    build_opportunity_monitor_report,
    console_safe_opportunity_message,
    read_opportunity_state,
    write_opportunity_state,
)
from paper_engine.reporting import write_report
from paper_engine.research_gate import (
    EvidencePreset,
    ascii_research_gate_report,
    assess_paper_rotation,
    evidence_from_preset,
    format_research_gate_report,
)
from paper_engine.runner import DEFAULT_DATA_DIR, DEFAULT_TOP_N, PaperRunConfig, run_once

app = typer.Typer(help="paper engine: TAN과 분리된 paper-only shadow runtime")
console = Console()


@app.command()
def once(
    top_n: Annotated[int, typer.Option("--top-n")] = DEFAULT_TOP_N,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
) -> None:
    summary = anyio.run(run_once, PaperRunConfig(data_dir=data_dir, top_n=top_n))
    message = (
        f"paper once done | scanned={summary.scanned} signals={summary.signals} "
        f"opened={summary.opened} blocked={summary.blocked} closed={summary.closed} "
        f"shadow={summary.shadow_evaluations} flip={summary.flip_alerts} "
        f"micro={summary.micro_snapshots} adaptive={summary.adaptive_decisions} data={data_dir}"
    )
    console.print(message)


@app.command()
def loop(
    top_n: Annotated[int, typer.Option("--top-n")] = DEFAULT_TOP_N,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
    interval_seconds: Annotated[int, typer.Option("--interval-seconds")] = 300,
) -> None:
    anyio.run(run_loop, PaperRunConfig(data_dir=data_dir, top_n=top_n), interval_seconds)


async def run_loop(config: PaperRunConfig, interval_seconds: int) -> None:
    while True:
        summary = await run_once(config)
        message = (
            f"paper loop | scanned={summary.scanned} signals={summary.signals} "
            f"opened={summary.opened} blocked={summary.blocked} closed={summary.closed} "
            f"shadow={summary.shadow_evaluations} flip={summary.flip_alerts} "
            f"micro={summary.micro_snapshots} adaptive={summary.adaptive_decisions} data={config.data_dir}"
        )
        console.print(message)
        await send_discord_report_when_enabled(config.data_dir)
        await anyio.sleep(interval_seconds)


@app.command()
def report(
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
) -> None:
    paper_report = write_report(data_dir)
    message = (
        f"paper report | open={paper_report.open_positions} "
        f"closed={paper_report.trades.closed} pnl_r={paper_report.trades.total_pnl_r:.2f} "
        f"win_rate={paper_report.trades.win_rate:.2%} data={data_dir / 'paper_report.json'}"
    )
    console.print(message)


@app.command("research-gate")
def research_gate(
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
    evidence: Annotated[EvidencePreset, typer.Option("--evidence")] = EvidencePreset.NONE,
    promotion_bundle: Annotated[Path | None, typer.Option("--promotion-bundle")] = None,
    send_discord: Annotated[bool, typer.Option("--send-discord/--dry-run")] = False,
    channel_id: Annotated[str | None, typer.Option("--channel-id")] = None,
) -> None:
    paper_report = write_report(data_dir)
    bundle_path = promotion_bundle or data_dir / "promotion_bundle.json"
    assessment = assess_paper_rotation(paper_report, evidence_from_preset(evidence), promotion_bundle_path=bundle_path)
    message = (
        format_research_gate_report(assessment)
        if stdout_supports_emoji()
        else ascii_research_gate_report(assessment)
    )
    console.print(message)
    if send_discord:
        result = anyio.run(send_paper_discord_text, message, None, channel_id)
        console.print(f"paper research discord sent | channel={result.channel_id} status={result.status_code}")


@app.command("opportunity-monitor")
def opportunity_monitor(
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
    send_discord: Annotated[bool, typer.Option("--send-discord/--dry-run")] = False,
    channel_id: Annotated[str | None, typer.Option("--channel-id")] = None,
    min_confidence: Annotated[float, typer.Option("--min-confidence")] = 0.45,
    cooldown_minutes: Annotated[int, typer.Option("--cooldown-minutes")] = 60,
) -> None:
    now_ms = int(time.time() * 1000)
    state_path = data_dir / "paper_opportunity_state.json"
    paper_report = write_report(data_dir)
    monitor_report = build_opportunity_monitor_report(
        OpportunityMonitorInput(
            paper_report=paper_report,
            config=OpportunityMonitorConfig(min_confidence=min_confidence, cooldown_minutes=cooldown_minutes),
            previous_state=read_opportunity_state(state_path),
            now_ms=now_ms,
            freshness=build_paper_freshness(data_dir),
        )
    )
    console_message = (
        monitor_report.message
        if stdout_supports_emoji()
        else console_safe_opportunity_message(monitor_report.message)
    )
    console.print(console_message)
    if not send_discord:
        return
    if not monitor_report.should_alert:
        skip_message = (
            f"paper opportunity discord skipped | candidates={monitor_report.candidate_count} "
            + f"fingerprint={monitor_report.fingerprint}"
        )
        console.print(
            skip_message
        )
        return
    result = anyio.run(send_paper_discord_text, monitor_report.message, None, channel_id)
    write_opportunity_state(state_path, OpportunityAlertState(monitor_report.fingerprint, now_ms))
    console.print(f"paper opportunity discord sent | channel={result.channel_id} status={result.status_code}")


def stdout_supports_emoji() -> bool:
    encoding = (sys.stdout.encoding or "").lower().replace("-", "")
    return encoding in {"utf8", "utf8sig"}


@app.command("discord-report")
def discord_report(
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
    send: Annotated[bool, typer.Option("--send/--dry-run")] = False,
    channel_id: Annotated[str | None, typer.Option("--channel-id")] = None,
) -> None:
    if send:
        result = anyio.run(send_paper_discord_report, data_dir, None, channel_id)
        console.print(f"paper discord sent | channel={result.channel_id} status={result.status_code}")
        return
    console.print(preview_paper_discord_report(data_dir))


def paper_discord_enabled() -> bool:
    return os.environ.get("PAPER_DISCORD_REPORT", "1").strip().lower() not in {"0", "false", "no", "off"}


async def send_discord_report_when_enabled(data_dir: Path) -> None:
    if not paper_discord_enabled():
        return
    try:
        result = await send_paper_discord_report(data_dir)
    except DiscordConfigError:
        return
    except httpx2.HTTPError as exc:
        console.print(f"paper discord failed | {type(exc).__name__}: {exc}")
        return
    console.print(f"paper discord sent | channel={result.channel_id} status={result.status_code}")


@app.command("news-add")
def news_add(
    event_json: Annotated[str, typer.Argument()],
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
) -> None:
    event = parse_news_event_json(event_json, int(time.time() * 1000))
    PaperLedger(data_dir).append_news(event)
    _ = write_report(data_dir)
    console.print(f"paper news added | symbol={event.symbol} source={event.source} data={data_dir}")

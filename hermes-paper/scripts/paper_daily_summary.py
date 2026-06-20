#!/usr/bin/env python3
"""YALRU Paper daily briefing → Discord (PAPER-일일보고).

stdlib + notify_relay only. tan venv에서 실행 (pytz/aiohttp 포함).
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/srv/hermes-os/paper/src")
sys.path.insert(0, "/srv/hermes-os/tan")
sys.path.insert(0, "/srv/hermes-os")

from tan.utils.notify_relay import send_discord as _notify_send

KST = timezone(timedelta(hours=9))

DATA_DIR = Path("/srv/hermes-os/paper/data")
TRADES_PATH = DATA_DIR / "paper_trades.jsonl"
REPORT_PATH = DATA_DIR / "paper_report.json"
PROMOTION_BUNDLE = DATA_DIR / "promotion_bundle.json"


def _notify(content: str, kind: str) -> int:
    try:
        result = _notify_send(content, kind=kind)
        if isinstance(result, dict):
            return int(result.get("status", 0) or 0) or 200
        return 200
    except Exception as exc:
        print(f"  notify_relay err: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue
        try:
            out.append(json.loads(stripped_line))
        except json.JSONDecodeError:
            continue
    return out


def _ms_to_kst(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=KST).strftime("%m-%d %H:%M")


def _trade_pnl_quote(t: dict) -> float:
    """Realized PnL in quote currency. Schema uses pnl_quote (paper engine)."""
    for key in ("pnl_quote", "pnl_usdt", "realized_pnl", "pnl"):
        if key in t and t[key] is not None:
            try:
                return float(t[key])
            except (ValueError, TypeError):
                pass
    return 0.0


def _trade_pnl_r(t: dict) -> float:
    for key in ("pnl_r", "r_multiple", "r"):
        if key in t and t[key] is not None:
            try:
                return float(t[key])
            except (ValueError, TypeError):
                pass
    return 0.0


def build_daily_briefing() -> str:  # noqa: PLR0915 - inherited formatter kept stable for paper daily report
    now_kst = datetime.now(KST)
    cutoff_ms = int((now_kst - timedelta(hours=24)).timestamp() * 1000)

    report = {}
    if REPORT_PATH.exists():
        try:
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = {}

    trades_all = _load_jsonl(TRADES_PATH)
    trades_24h = [
        t for t in trades_all
        if int(t.get("exit_time_ms", 0) or t.get("entry_time_ms", 0) or 0) >= cutoff_ms
    ]

    realized_pnl = sum(_trade_pnl_quote(t) for t in trades_24h)
    realized_r = sum(_trade_pnl_r(t) for t in trades_24h)
    wins = [t for t in trades_24h if _trade_pnl_quote(t) > 0]
    losses = [t for t in trades_24h if _trade_pnl_quote(t) < 0]
    win_rate = (len(wins) / len(trades_24h) * 100) if trades_24h else 0.0

    open_rows = report.get("open_position_rows", []) or {}

    latest_run = report.get("latest_run", {}) or {}
    block_reasons = report.get("block_reasons", []) or []
    flip = report.get("latest_flip", {}) or {}
    aggregate = report.get("trades", {}) or {}
    agg_pnl = float(aggregate.get("total_pnl_quote", 0.0) or 0.0)
    agg_r = float(aggregate.get("total_pnl_r", 0.0) or 0.0)
    agg_win_rate = float(aggregate.get("win_rate", 0.0) or 0.0) * 100
    agg_closed = int(aggregate.get("closed", 0) or 0)

    lines = [
        f"📊 **PAPER 일일 브리핑** [{now_kst.strftime('%Y-%m-%d %H:%M')} KST]",
        "━━━━━━━━━━━━━━━━━",
        f"💰 **24h 실현 손익**: {realized_pnl:+.4f}U ({realized_r:+.2f}R)",
        f"📈 **현재 open**: {len(open_rows)}개",
        f"🎯 **24h 청산**: {len(trades_24h)}건 (승 {len(wins)} / 패 {len(losses)} | 승률 {win_rate:.1f}%)",
        f"📦 **누적 집계**: 청산 {agg_closed}건 | 손익 {agg_pnl:+.4f}U ({agg_r:+.2f}R) | 승률 {agg_win_rate:.1f}%",
    ]

    if trades_24h:
        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append("📋 **최근 청산 내역**")
        for t in trades_24h[-5:]:
            sym = t.get("symbol", "?")
            side = t.get("side", "?")
            entry = float(t.get("entry_price", 0) or 0)
            exit_p = float(t.get("exit_price", 0) or 0)
            stop = t.get("stop_price")
            tp = t.get("take_profit_price")
            pnl_q = _trade_pnl_quote(t)
            pnl_r = _trade_pnl_r(t)
            reason = t.get("reason") or t.get("exit_reason") or "?"
            icon = "✅" if pnl_q >= 0 else "❌"
            entry_t = _ms_to_kst(int(t.get("entry_time_ms", 0) or 0))
            line = (
                f"{icon} {sym} {side} | 진입 {entry:.8g} → 청산 {exit_p:.8g} | "
                f"{reason} | {pnl_q:+.4f}U ({pnl_r:+.2f}R)"
            )
            if stop is not None:
                line += f" | SL {float(stop):.8g}"
            if tp is not None:
                line += f" | TP {float(tp):.8g}"
            line += f" | @{entry_t}"
            lines.append(line)

    if open_rows:
        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append("📂 **현재 open positions**")
        for r in open_rows[:5]:
            sym = r.get("symbol", "?")
            side = r.get("side", "?")
            entry = float(r.get("entry_price", 0) or 0)
            stop = r.get("stop_price")
            tp = r.get("take_profit_price")
            icon = "📈" if str(side).upper() == "LONG" else "📉"
            line = f"{icon} {sym} {side} | 진입 {entry:.8g}"
            if stop is not None:
                line += f" | SL {float(stop):.8g}"
            if tp is not None:
                line += f" | TP {float(tp):.8g}"
            lines.append(line)

    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append(
        f"🛰 **최근 scan**: {latest_run.get('scanned', 0)}심볼 | "
        f"신호 {latest_run.get('signals', 0)} | "
        f"진입 {latest_run.get('opened', 0)} | "
        f"차단 {latest_run.get('blocked', 0)} | "
        f"청산 {latest_run.get('closed', 0)}"
    )

    if block_reasons:
        top = ", ".join(f"{b.get('name', '?')} {b.get('count', 0)}" for b in block_reasons[:3])
        lines.append(f"🚫 **차단 이유**: {top}")

    if flip:
        state = flip.get("state", "?")
        icon = {
            "NORMAL": "🟡", "RISK_OFF": "🔴", "PANIC_SHORT": "🔴",
            "RECOVERY_LONG": "🟢",
        }.get(state, "⚪")
        lines.append(
            f"🌐 **시장 상태**: {icon} {state} "
            f"(short_flip {flip.get('short_flip_score', 0):.2f})"
        )

    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append("🧪 PAPER 엔진 = 실험실. 좋은 조건 발견 시 paper승격제안 채널로 자동 제안.")
    return "\n".join(lines)[:2000]


def format_promotion_proposal(bundle: dict) -> str:
    status = bundle.get("promotion_bundle_status", "UNKNOWN")
    gate = bundle.get("paper_gate_verdict", "UNKNOWN")
    approval = bundle.get("live_approval_state", "UNKNOWN")
    candidate = bundle.get("candidate", {}) or {}
    metrics = bundle.get("metrics", {}) or {}
    artifacts = bundle.get("artifacts", {}) or {}

    symbol = candidate.get("symbol", "?")
    side = candidate.get("side", "?")
    wfa = metrics.get("wfa_sharpe", "?")
    oos = metrics.get("oos_return", "?")
    pbo = metrics.get("pbo", "?")
    mc = metrics.get("monte_carlo_pct", "?")
    artifact_count = len([v for v in artifacts.values() if v])

    return "\n".join([
        "🚀 **PAPER 승격 제안**",
        f"📊 상태: {status} | 게이트: {gate} | 라이브 승인: {approval}",
        f"💱 후보: {symbol} | side: {side}",
        f"📈 WFA: {wfa} | OOS: {oos} | PBO: {pbo} | MC: {mc}",
        f"📦 증거 아티팩트: {artifact_count}개",
        "🧯 paper→live 승격 후보. live 진입은 별도 C5 승인 필요. 자동 진입 안 함.",
    ])


async def main() -> int:
    if not DATA_DIR.exists():
        print(f"data dir missing: {DATA_DIR}", file=sys.stderr)
        return 1

    briefing = build_daily_briefing()
    print("--- daily briefing ---")
    print(briefing[:600])

    print("--- sending daily briefing to PAPER channel ---")
    sc = _notify(briefing, kind="paper")
    print(f"sent status={sc}")

    if PROMOTION_BUNDLE.exists():
        try:
            bundle = json.loads(PROMOTION_BUNDLE.read_text(encoding="utf-8"))
            status = str(bundle.get("promotion_bundle_status", "")).upper()
            approval = str(bundle.get("live_approval_state", "")).upper()
            if status in {"PASSING", "AWAITING_C5"} or approval == "AWAITING_C5":
                proposal = format_promotion_proposal(bundle)
                print("--- sending promotion proposal ---")
                sc2 = _notify(proposal, kind="promotion")
                print(f"promotion status={sc2}")
            else:
                print(f"--- bundle {status}/{approval} - skip ---")
        except Exception as exc:
            print(f"promotion failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    else:
        print("--- no promotion bundle, skip ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

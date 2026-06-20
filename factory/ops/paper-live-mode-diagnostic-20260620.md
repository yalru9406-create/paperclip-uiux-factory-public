# Paper/Live Mode Diagnostic - 2026-06-20

## Work Packet

- Actual goal: record a safe diagnostic report for why paper and live modes feel wrong, without changing trading behavior.
- Risk level: C5 adjacent. Live trading/money services were observed read-only only.
- Scope used: wrote only this ops report plus evidence files under `.omo/evidence/`.
- Must not do: no live order, cancel, close, sizing, leverage, margin, stop, take-profit, exchange configuration, credential/env value, DB/state mutation, service restart, Discord router edit, dashboard edit, or paper engine code edit.
- Done definition: redacted service state, journal/log snippets, identity reconciliation checklist, C5-blocked list, and paper-only restart/rollback policy recorded with command transcript evidence.

## Hypotheses

1. Paper crash source is an upstream Binance futures ticker fetch failure. The direct paper error log shows `/fapi/v1/ticker/24hr` followed by `RemoteProtocolError`.
2. Paper being active but not opening is currently a gate outcome, not proof that the service is stopped. Paper loop summaries show repeated `opened=0 blocked=...`, and the paper block event tail is dominated by `duplicate_signal`, `existing_position`, and `entry_gate`.
3. Live identity is confusing because the systemd unit still carries an older aggressive description and earlier drop-ins, while the final effective command comes from `zz-exact-bot.conf` and runs `true_turtle_exact/bot.py`.
4. The live risk manager is observing live mode but not taking live actions. Its logs report `mode=live`, current observed positions, and `activations_attempted=0` / `activations_succeeded=0`.
5. The live sentinel is read-only and reports active live positions, so the operator can see exposure while other live components appear quiet.

## Evidence Snippets

All snippets below are redacted and summarized from `.omo/evidence/paper-live-mode-diagnostic-20260620-commands.log`.

- Service activity check: `paper.service`, `tan-live.service`, `tan-live-risk-manager.service`, and `tan-live-sentinel.service` all returned `active`.
- Paper unit: `Description=paper engine - separate paper-only shadow runtime`; `ExecStart=/root/.local/bin/uv run python -m paper_engine loop --top-n 50 --data-dir /srv/hermes-os/paper/data --interval-seconds 300`.
- Paper crash evidence: paper error log contains `/fapi/v1/ticker/24hr` and `RemoteProtocolError: <ConnectionTerminated ...>`.
- Paper loop evidence: repeated lines include `paper loop | scanned=50 signals=3 opened=0 blocked=3 closed=0 shadow=18 flip=0`.
- Paper block reason summary from the last 80 paper block events: `duplicate_signal=25`, `entry_gate=5`, `existing_position=7`.
- Live unit identity: base description says older aggressive no-WLD seed persona, but the final drop-in sets `WorkingDirectory=/srv/hermes-os/tan/true_turtle_exact` and a redacted bootstrap that execs `/srv/hermes-os/tan/true_turtle_exact/bot.py`.
- Live risk manager: journal lines show `mode=live`, observed positions, decisions, `activations_attempted=0`, and `activations_succeeded=0`.
- Live sentinel: journal lines state the sentinel is read-only and show an active position observation.

## Current Interpretation

Paper is active now, but the recent history has two separate symptoms: an earlier crash/restart path from the Binance ticker request, and a current no-open path caused by normal paper gate decisions. The no-open path is explainable from verified paper-only block events rather than from service inactivity.

Live appears operational but identity-confusing. The human-facing unit description and earlier drop-ins still describe the older aggressive config, while systemd's final effective command is the exact turtle bot. That mismatch can make live mode feel wrong even when the effective process is the intended one. The risk manager and sentinel are also not equivalent to the live bot: the risk manager is dry-run/no-action by description and log behavior, while the sentinel is read-only observation.

## Safe Next Fixes

- Paper fetch resilience: add paper-only retry/backoff and explicit handling for `RemoteProtocolError` around the Binance ticker call, then verify with a targeted failing test and a paper CLI/service smoke. This was not implemented in this task because code edits were out of scope.
- Paper gate observability: add a paper-only summary line that reports block reason counts per loop so `opened=0 blocked=N` immediately explains whether the block is duplicate, existing position, or entry gate.
- Paper duplicate policy review: inspect whether `signal_key` time bucketing and duplicate suppression are intentionally broad. Keep this paper-only until proven.
- Paper existing-position policy review: confirm whether one open paper position per symbol is intended. Do not loosen this without an explicit paper risk note.
- Paper entry gate review: compare weak breakout thresholds against the current market regime before changing any thresholds.
- Live identity reconciliation: perform the read-only checklist below first. Any unit/drop-in description cleanup or live service restart must be separately approved.

## C5-Blocked Items

The following require fresh, explicit, scoped approval before any action:

- Any live order placement, cancellation, close, reduce, resize, stop change, take-profit change, leverage change, margin change, or exchange account/config change.
- Any live position mutation, including protective-order mutation. Live position mutation requires fresh explicit approval naming the service, account, symbol(s), intended action, rollback/abort condition, and verification steps.
- Any read or write of credential/env values beyond redacted path/name-level service inspection.
- Any DB/state mutation for live or paper runtimes.
- Any restart/stop/start/reload of `tan-live.service`, `tan-live-risk-manager.service`, `tan-live-sentinel.service`, Discord router, dashboard, or exchange-facing live process.
- Any edit under `/srv/hermes-os/tan`, service units, Discord router, dashboard, paper engine code, or protected runtime config.

## Paper-Only Restart/Rollback Policy

No restart was performed for this report. If a future paper-only fix is approved and implemented, the restart policy is:

1. Scope: `paper.service` only. Do not touch any `tan-live*` service.
2. Preflight: record `systemctl is-active paper.service`, `systemctl show paper.service -p ActiveEnterTimestamp -p NRestarts -p ExecMainPID`, and the last paper log/error snippets.
3. Apply only the approved paper-only change.
4. Restart: run `systemctl restart paper.service` once.
5. Verify: require `systemctl is-active paper.service` to return `active`, inspect fresh paper log lines for a loop summary, and confirm no immediate traceback or repeated restart.
6. Rollback: if paper fails to become active or immediately crashes, revert only the approved paper change, run `systemctl restart paper.service` once, and repeat the same active/log verification.
7. Escalate: if rollback fails, stop further service control and report the exact active state, recent journal tail, changed file path, and rollback attempt result.

## Tan-Live Identity Reconciliation Checklist (Read-Only)

Compare these fields without editing or restarting anything:

- `systemctl cat tan-live.service`: base `Description=`, all drop-in file names, and final effective `WorkingDirectory=` / `ExecStart=` after later drop-ins.
- Drop-in order: verify whether `zz-exact-bot.conf` is the last effective command override and whether older alpha/no-WLD comments are stale identity labels.
- Command identity: compare final command path (`true_turtle_exact/bot.py`) to any config path still visible from earlier overridden `ExecStart=` lines.
- Runtime logs: compare live bot log fields/persona labels, risk manager `mode`, and sentinel status text to the final systemd command.
- Risk manager behavior: confirm whether `Description=TAN LIVE Risk Manager - dry-run only (no live action)` matches log fields `activations_attempted=0` and `activations_succeeded=0`.
- Sentinel behavior: confirm sentinel remains read-only and reports observations only.
- Operator-facing identity: only after read-only reconciliation, propose a separate approved unit/drop-in description cleanup if the effective command is correct but labels are stale.

## Evidence and Cleanup

- Command transcript: `.omo/evidence/paper-live-mode-diagnostic-20260620-commands.log`.
- Consolidated evidence entry: `.omo/evidence/paper-live-mode-diagnostic-20260620.md`.
- Cleanup receipt: no background process, tmux session, service restart, service control action, code edit, DB/state mutation, or live trading mutation was performed.

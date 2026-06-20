# Hermes Discord Agent Router Configuration Plan

## Goal

Connect the local `discord-agent-router` registry to Hermes/Yalru OS without adding unsafe execution authority. This is a configuration plan only; applying it requires a separate scoped approval before any remote service write or restart.

## Safety boundaries

- Do not print, echo, log, capture, or commit Discord bot tokens, Hermes env values, API keys, cookies, or private auth files.
- `dangerousExecutionBridge` must stay `false` in `agents.yaml`, normalized router output, and Yalru OS intake dry-run payloads.
- C4 boundary: Discord tokens and Hermes secret stores are private data. Inspect only key names and file presence unless fresh scoped approval authorizes secret handling with redaction.
- C5 boundary: TAN live strategy, orders, positions, exchange state, and money-moving services are out of scope. Do not mutate TAN or trading systems from this router.
- GLM lanes (`freeclaude-glm`, `gajecode`) remain queued/degraded until quota and keys are explicitly restored.

## one-dispatcher mode

Use one existing Hermes Discord gateway identity as the visible dispatcher. Per-agent chat windows are Discord channels or threads mapped by route key.

Non-secret config keys/names:

- `DISCORD_AGENT_ROUTER_ENABLED=true`
- `DISCORD_AGENT_ROUTER_MODE=one_dispatcher`
- `DISCORD_AGENT_ROUTER_REGISTRY=/srv/paperclip-data/multiagent-uiux-factory/discord-agent-router/agents.yaml`
- `DISCORD_AGENT_ROUTER_ALLOWED_THREAD_IDS=1517721645811499099`
- `DISCORD_AGENT_ROUTER_DEFAULT_BRIDGE_ENABLED=false`
- `DISCORD_AGENT_ROUTER_INTAKE_MODE=dry_run`
- `DISCORD_AGENT_ROUTER_LOG_REDACTION=strict`
- `YALRU_OS_INTAKE_CONTRACT=discord_agent_router_dry_run`

Expected behavior:

- Hermes receives Discord messages through the already-approved gateway.
- Router normalizes envelopes locally and preserves `sourceRef`, `payloadHash`, `discordThreadId`, and `agentRoute`.
- Ready lanes can be handed to local adapters only after the orchestrator approves the downstream action.
- Degraded GLM lanes are queued and must not call GLM while quota is exhausted.

## optional multi-token mode

Use only if separate visible bot accounts are required. Discord requires a separate Developer Portal application and token per bot identity.

Non-secret config keys/names:

- `DISCORD_AGENT_ROUTER_ENABLED=true`
- `DISCORD_AGENT_ROUTER_MODE=multi_token`
- `DISCORD_AGENT_ROUTER_REGISTRY=/srv/paperclip-data/multiagent-uiux-factory/discord-agent-router/agents.yaml`
- `DISCORD_AGENT_ROUTER_DEFAULT_BRIDGE_ENABLED=false`
- `DISCORD_AGENT_ROUTER_INTAKE_MODE=dry_run`
- `DISCORD_AGENT_ROUTER_LOG_REDACTION=strict`
- `DISCORD_BOT_TOKEN_LAZYCODEX` secret value stored only in Hermes/VPS secret storage
- `DISCORD_BOT_TOKEN_FREECLAUDE_GLM` secret value stored only in Hermes/VPS secret storage
- `DISCORD_BOT_TOKEN_GAJECODE` secret value stored only in Hermes/VPS secret storage
- `DISCORD_BOT_TOKEN_ANTIGRAVITY` secret value stored only in Hermes/VPS secret storage
- `DISCORD_AGENT_ROUTER_LAZYCODEX_ALLOWED_THREAD_IDS`
- `DISCORD_AGENT_ROUTER_FREECLAUDE_GLM_ALLOWED_THREAD_IDS`
- `DISCORD_AGENT_ROUTER_GAJECODE_ALLOWED_THREAD_IDS`
- `DISCORD_AGENT_ROUTER_ANTIGRAVITY_ALLOWED_THREAD_IDS`

Do not place token values in this repository, shell history, screenshots, logs, or evidence files. Record only the existence of secret key names and redacted target paths.

## Backup, validate, restart, smoke

Run these only after scoped approval for Hermes config mutation and restart:

1. Backup current config without printing secrets:
   - `install -m 0600 /root/.hermes/.env /root/.hermes/.env.bak-YYYYMMDD-HHMMSS`
   - If Hermes uses YAML, copy that file with the same timestamped backup pattern.
2. Edit only the required non-secret config keys and secret key names. Never paste token values into terminal output.
3. Validate registry syntax:
   - `python3 -m json.tool /srv/paperclip-data/multiagent-uiux-factory/discord-agent-router/agents.yaml >/dev/null`
4. Validate router behavior without live calls:
   - `python3 -m unittest discover -s /srv/paperclip-data/multiagent-uiux-factory/discord-agent-router -p 'test_*.py'`
   - `python3 /srv/paperclip-data/multiagent-uiux-factory/discord-agent-router/router.py < sanitized-envelope.json`
   - `python3 /srv/paperclip-data/multiagent-uiux-factory/discord-agent-router/intake_client.py < normalized-router.json --summary`
5. Restart hermes-gateway only inside the approved restart window:
   - `systemctl restart hermes-gateway`
6. Smoke active state and route behavior:
   - `systemctl is-active hermes-gateway`
   - Send one approved Discord test message to a whitelisted thread.
   - Confirm the evidence contains route key, sourceRef, payloadHash, queued/ready status, and `dangerousExecutionBridge=false`.
   - Confirm evidence does not contain token values or raw author IDs.

## rollback

If validation, restart, or smoke fails:

1. Restore the timestamped Hermes config backup without printing file contents.
2. Run the same syntax validation command.
3. Restart hermes-gateway within the same scoped approval window.
4. Confirm `systemctl is-active hermes-gateway` returns `active`.
5. Record the failed command, restored backup path, active-state check, and residual risk in router evidence.

## Completion evidence

A safe completion record includes:

- Test command output path.
- Dry-run router JSON path for `lazycodex` and `freeclaude-glm`.
- Dry-run intake JSON path for `lazycodex` and `freeclaude-glm`.
- Secret scan command and output path for changed files only.
- Cleanup receipt stating no temp files, background processes, service restarts, TAN mutation, or live Discord admin mutation were performed.

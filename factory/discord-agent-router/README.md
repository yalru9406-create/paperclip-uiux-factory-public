# Discord Agent Router

Safe MVP for Discord-first per-agent chat windows.

## Lanes

- `orchestrator` — Hermes Orchestrator / Hermes Top Orchestrator / ready
- `lazycodex` — LazyCodex Bot / LazyCodex GPT Lane / ready
- `freeclaude-glm` — FreeClaude[GLM] Bot / FreeClaude GLM 5.2 Critic / degraded while GLM quota is exhausted
- `gajecode` — GajeCode Bot / GajeCode GLM 5.2 Engineer / degraded while GLM quota is exhausted
- `antigravity` — Antigravity Bot / Gemini Antigravity Lane / ready

## Live Discord surfaces

The current implementation uses one Hermes/Yalru dispatcher and separate Discord channels as the individual chat windows. This avoids requiring four new Discord bot tokens while still giving mobile users clear per-agent surfaces.

Verified channels:

- `#agent-orchestrator` — `1517790192516206632`
- `#agent-lazycodex` — `1517790167090594002`
- `#agent-freeclaude-glm` — `1517790172756840468`
- `#agent-gajecode` — `1517790179606138961`
- `#agent-antigravity` — `1517790186191458376`

## Safety

- `dangerousExecutionBridge` is always `false` in the registry and normalized payload.
- GLM lanes queue/degrade while quota is exhausted; they do not silently call GLM.
- Author IDs are hashed in normalized payloads.
- This router does not call Discord or execute agents. It is a deterministic normalization layer for dry-run/integration QA.
- Do not store Discord tokens here. Secrets stay in Hermes/VPS secret stores.

## Test

```bash
python3 -m unittest discover -s discord-agent-router -p 'test_*.py'
```

## Dry-run example

```bash
python3 discord-agent-router/router.py <<'JSON'
{
  "agentRoute": "lazycodex",
  "message": "run safe Paperclip QA",
  "discordThreadId": "1517721645811499099",
  "discordMessageId": "1234567890",
  "authorId": "example-user"
}
JSON
```

## Future live Discord integration

1. Keep one-dispatcher mode as the default unless distinct visible bot identities are required.
2. If separate bot identities are required, create Discord Developer Portal applications and add tokens to the VPS secret store; never place tokens in this directory.
3. Restart gateway only after backing up config and verifying YAML/env syntax.

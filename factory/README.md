# YALRU Paperclip MultiAgent UI/UX Factory

This factory turns a rough UI/UX request into a Paperclip issue tree and a durable file-based workspace.

It is designed for:

- GLM 5.2 visual draft lanes.
- Codex/GPT implementation and QA lanes.
- Antigravity screenshot/document review lanes.
- Hermes orchestration.
- Append-only logs, approval records, and evidence folders.

It does not modify the upstream Paperclip package. It lives under `/srv/paperclip-data/multiagent-uiux-factory` and uses the existing Paperclip CLI/API.

## Main Command

```bash
yalru-uiux-factory new \
  --slug bottom-cta \
  --goal "Implement a Toss-style BottomCTA mobile flow" \
  --target-repo "/path/to/repo" \
  --write-scope "src/components/BottomCTA*,src/app/*" \
  --approval-text "User approved writes only inside the provided write scope for this run." \
  --screens 3 \
  --stack "React/Next.js"
```

## Status

```bash
yalru-uiux-factory doctor
yalru-uiux-factory status <run-dir>
yalru-uiux-factory capture-evidence <run-dir>
```

## Agent Room Chat

Paperclip already supports issue comments and `agent prompt --issue`.
The factory binds that into a persistent Agent Room issue, so the operator can keep one room open in Paperclip and still route messages to a specific agent from CLI.

```bash
yalru-uiux-factory provision-agent-keys
yalru-uiux-factory room ensure
yalru-uiux-factory room status
yalru-uiux-factory room send --agent hermes --message "Break this request into a Work Packet."
yalru-uiux-factory chat gajecode --message "Draft the mobile screen states."
yalru-uiux-factory antigravity --message "Review the attached screenshots."
```

Use `--no-wake` for smoke tests or notes that should be attached without starting an agent run.

## Agent Dashboard CLI Panel

Runbook: `agent-dashboard-cli/RUNBOOK.md`.

Correct health check through Nginx is `/yalru-agent-cli/health` (the sidecar exposes `/health` behind the `/yalru-agent-cli/` proxy prefix). The browser panel is injected through `/yalru-agent-cli/panel.js` and appears as a `CLI` tab on `/YAL/agents/<agent-url-key>/dashboard` pages.


The VPS install also mounts a small same-origin panel on each Paperclip agent dashboard page:

```text
/YAL/agents/<agent-url-key>/dashboard
```

The panel calls `/yalru-agent-cli/api/*`, which is a loopback-only sidecar. It only runs whitelisted factory commands for the current agent:

```bash
yalru-uiux-factory <agent-key> --message "<message>" --no-wake
yalru-uiux-factory <agent-key> --message "<message>"
```

`Attach` writes a Paperclip comment without waking execution. `Send + Wake` routes the message through the agent persona and wakes that agent.

## Memory Layout

Each run creates:

- `task.md`
- `context.md`
- `brief.md`
- `log.md`
- `approval.md`
- `result.md`
- `DESIGN.md`
- `artifacts/`
- `sources/`
- `evidence/`

The room state is stored at `rooms/state.json` after `room ensure`.
Agent API keys for directed chat are stored in `config/agent-api.env` with mode `0600` after `provision-agent-keys`; values are not printed by the factory.

## Security Defaults

- External repo writes are blocked unless approval is recorded.
- `target_repo` and `write_scope` alone do not create approval; `--approval-text` is required.
- OAuth/subscription adapters are preferred.
- Paid API key usage is not part of this factory.
- Paperclip remains on loopback behind the existing Nginx/Basic Auth setup.

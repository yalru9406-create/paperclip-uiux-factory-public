# Paperclip Agent Dashboard CLI - VPS Runbook

_Last updated: 2026-06-20 KST_

## Purpose

Paperclip stays upstream-compatible. The Yalru Agent Dashboard CLI is a VPS-only same-origin sidecar that adds a `CLI` tab to Paperclip agent dashboard pages so mobile/desktop operators can attach messages, wake agents, inspect adapter auth, and open a whitelisted command-runner fallback without exposing raw credentials.

## Live endpoints

- Public Paperclip UI: `https://paperclip.46.250.229.212.sslip.io/`
- Agent dashboard example: `https://paperclip.46.250.229.212.sslip.io/YAL/agents/hermes-top-orchestrator/dashboard`
- Injected script: `/yalru-agent-cli/panel.js`
- Correct sidecar health through nginx: `/yalru-agent-cli/health`
- Sidecar API prefix: `/yalru-agent-cli/api/*`
- Sidecar loopback service: `127.0.0.1:4192`
- Paperclip upstream app: `127.0.0.1:4191`

## One-command VPS QA

Run this after Paperclip Agent CLI work and attach the log to evidence:

```bash
cd /srv/paperclip-data/multiagent-uiux-factory
mkdir -p /tmp/paperclip-agent-cli-evidence
agent-dashboard-cli/qa-vps.sh | tee /tmp/paperclip-agent-cli-evidence/20260620-vps-qa-paperclip-agent-cli-script.log
```

Expected: exit 0 and `overall=PASS`. The script runs only safe checks: Python compile, project doctor, `sudo -n nginx -t`, service active state, route/content assertions, `/yalru-agent-cli/api/public-status` assertions, nginx route-shape checks, the preconfigured Discord mobile thread ID from operator context only, and TAN read-only status. It does not restart services, read or dump root env/config files, print tokens, mutate TAN, or push git.

The script does not run browser automation. Keep the Chrome/Playwright visual QA JSON and screenshots as separate evidence. If a browser QA JSON is copied onto the VPS intentionally, set `BROWSER_QA_ARTIFACT` to that local VPS file path; a missing supplied path fails the QA script.

## Services

```bash
systemctl status yalru-agent-cli --no-pager
systemctl status nginx --no-pager
ss -ltnp | grep -E '4191|4192|80|443'
```

Expected: `yalru-agent-cli.service` active, Nginx reloadable, 4192 sidecar listening, and 4191 Paperclip app listening.

## Health-route pitfalls

- `server.py` exposes `/health`, not `/api/health`.
- Through nginx, the correct sidecar health check is `/yalru-agent-cli/health`.
- Do **not** use `/yalru-agent-cli/api/health` as health evidence. It is a pitfall route and the QA script records it only as a negative/non-health check.
- Do **not** use `http://127.0.0.1:4191/yalru-agent-cli/health` as sidecar health evidence. Port 4191 is the Paperclip upstream app; that prefixed path can return fallback Paperclip HTML instead of the sidecar JSON.
- Valid direct sidecar loopback health is `http://127.0.0.1:4192/health`.

## Nginx integration pitfalls fixed on 2026-06-20

- Do **not** nest `location = /yalru-agent-cli/panel.js` or `location /yalru-agent-cli/` inside `location /`.
- Do **not** use `add_header Content-Type ...` for JavaScript; use `default_type application/javascript`.
- Do **not** shell-expand `$host`, `$remote_addr`, or `$proxy_add_x_forwarded_for` when templating the file.
- Add `proxy_set_header Accept-Encoding "";` on the Paperclip upstream route so `sub_filter` can inject the panel script into HTML.
- After the explicit short terminal routes, add `location = /yalru-terminal { deny all; }` and `location ^~ /yalru-terminal/ { deny all; }` before `location /` so unknown terminal paths cannot fall through to the Paperclip SPA.
- Keep Nginx backups outside `/etc/nginx/sites-enabled`; files left there are loaded as live configs and can create duplicate `server_name` blocks.
- If a live nginx edit is truly required, back up first:

```bash
sudo mkdir -p /etc/nginx/backups
sudo cp /etc/nginx/sites-enabled/paperclip /etc/nginx/backups/paperclip.bak-$(date +%Y%m%d-%H%M%S)
sudo nginx -t
sudo systemctl reload nginx
curl -ksS -i https://127.0.0.1/yalru-agent-cli/health | sed -n '1,20p'
```

Do not reload nginx for docs, evidence, or QA-script-only work.

## Safe individual verification

```bash
cd /srv/paperclip-data/multiagent-uiux-factory
python3 -m py_compile agent-dashboard-cli/*.py
./bin/yalru-uiux-factory doctor
sudo -n nginx -t
systemctl is-active nginx hermes-gateway yalru-agent-cli tan-live tan-api
curl -ksS -i https://127.0.0.1/yalru-agent-cli/health | sed -n '1,20p'
curl -ksS -i 'https://127.0.0.1/yalru-agent-cli/api/context?agentRoute=hermes-top-orchestrator' | sed -n '1,20p'
curl -ksS -i https://127.0.0.1/yalru-agent-cli/api/public-status | sed -n '1,40p'
curl -ksS -i https://127.0.0.1/yalru-agent-cli/panel.js | sed -n '1,20p'
curl -ksS -i https://127.0.0.1/ | sed -n '1,20p'
curl -sS -i https://paperclip.46.250.229.212.sslip.io/yalru-agent-cli/health | sed -n '1,20p'
```

Expected: health returns JSON `{"ok": true}`, context returns Hermes route context JSON, public status returns `safety.liveMutationAllowed=false` and `privateControls.enabled=false`, panel script returns JavaScript, and root/dashboard HTML include `/yalru-agent-cli/panel.js`.

## Browser QA checklist

If browser automation is available, open an agent dashboard and verify:

1. `CLI` tab exists.
2. Clicking `CLI` creates `#yalru-agent-cli-panel`.
3. On public hosts, the panel shows Discord chat surfaces plus Public ops status with TAN LIVE visibility, `tan_mutation=not_performed`, PAPER artifact metadata, promotion gate/live approval state, VPS QA safety facts, and `Live mutation locked / C5` text.
4. On public hosts, the panel does not render private terminal, adapter auth, command runner, or agent message controls.
5. On loopback-style hosts only, private terminal, adapter auth, command runner, and agent message controls may render.
6. Short aliases such as `/YAL/agents/hermes#yalru-cli` redirect to the canonical dashboard route with `#yalru-cli` preserved.
7. Console has no JavaScript errors on the final rendered route.
8. The static script may not literally contain uppercase `AGENT TERMINAL`; runtime rendering and CSS transform are the browser proof.

Hermes already verified this browser surface on 2026-06-20; keep the checklist in future evidence if browser driving is unavailable.

PAPER status is independently inspectable with `paper status --data-dir /srv/hermes-os/paper/data --json`. It must report `safety.liveMutationAllowed=false`, a `promotionGate.liveApprovalState`, block-reason counts, and it must not write `paper_report.json`.

## Safety notes

- Status checks never print secret values.
- `Attach` comments without waking execution; `Send + Wake` wakes the selected agent lane.
- Hermes Discord mobile thread `1517721645811499099` is configured; never print Discord tokens.
- TAN live strategy, entry conditions, orders, and positions are unrelated to this panel and must not be changed by Paperclip UI work.

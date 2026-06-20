const PANEL_ID = "yalru-agent-cli-panel";
const TAB_ID = "yalru-agent-cli-tab";
const STYLE_ID = "yalru-agent-cli-style";
const API_BASE = "/yalru-agent-cli";
const CLI_HASH = "#yalru-cli";
const CLI_VALUE = "yalru-cli";
const RENDER_DELAY_MS = 750;
const ROUTE_PATTERN = /\/agents\/([^/?#]+)/;
const TERMINAL_ROUTE_ALIASES = {
  "freeclaude-glm-5-2-critic": "freeclaude",
  "gajecode-glm-5-2-engineer": "gajecode",
  "gemini-antigravity-lane": "antigravity",
  "hermes-top-orchestrator": "hermes",
  "lazycodex-gpt-lane": "lazycodex",
  "vps-qa-harness-glm": "qa",
};

let renderTimer = 0;
let terminalPollTimer = 0;

function agentRoute() {
  const match = window.location.pathname.match(ROUTE_PATTERN);
  return match ? decodeURIComponent(match[1]) : "";
}

function requestRender() {
  window.clearTimeout(renderTimer);
  renderTimer = window.setTimeout(render, RENDER_DELAY_MS);
}

function removePanel() {
  stopTerminalPoll();
  document.getElementById(PANEL_ID)?.remove();
}

async function render() {
  const route = agentRoute();
  if (!route) {
    removePanel();
    muteNativeTabs(false);
    document.getElementById(TAB_ID)?.remove();
    return;
  }
  ensureTab(route);
  if (!cliTabActive()) {
    removePanel();
    return;
  }
  const existingPanel = document.getElementById(PANEL_ID);
  if (existingPanel?.dataset.agentRoute === route) {
    return;
  }
  const context = await fetchContext(route);
  if (!context.ok) return;
  mountPanel(route, context);
}

async function fetchContext(route) {
  const response = await fetch(`${API_BASE}/api/context?agentRoute=${encodeURIComponent(route)}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  return response.json();
}

function mountPanel(route, context) {
  removePanel();
  ensureBaseStyle();
  const panel = document.createElement("section");
  panel.id = PANEL_ID;
  panel.dataset.agentRoute = route;
  panel.innerHTML = panelMarkup(context);
  panel.querySelector("[data-terminal-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    sendTerminalInput(route);
  });
  panel.querySelector("[data-action='terminal-start']")?.addEventListener("click", () => startTerminal(route));
  panel.querySelector("[data-action='terminal-refresh']")?.addEventListener("click", () => refreshTerminal(route));
  panel.querySelector("[data-action='terminal-clear']")?.addEventListener("click", () => clearTerminal(route));
  panel.querySelector("[data-action='terminal-restart']")?.addEventListener("click", () => restartTerminal(route));
  panel.querySelector("[data-action='adapter-status']")?.addEventListener("click", () => loadAdapterStatus(route));
  panel.querySelector("[data-action='adapter-reconnect']")?.addEventListener("click", () => runAdapterReconnect(route));
  panel.querySelector("[data-action='attach']")?.addEventListener("click", () => sendMessage(route, false));
  panel.querySelector("[data-action='wake']")?.addEventListener("click", () => sendMessage(route, true));
  panel.querySelector("[data-action='status']")?.addEventListener("click", () => loadStatus(route));
  panel.querySelectorAll("[data-discord-copy]").forEach((button) => { button.addEventListener("click", copyDiscordSurface); });
  placePanel(panel);
  if (canUsePrivateControls()) {
    startTerminal(route);
    startTerminalPoll(route);
  }
}

function cliTabActive() {
  return window.location.hash === CLI_HASH;
}

function ensureTab(route) {
  ensureBaseStyle();
  const tabRow = findTabRow();
  ensureSelectOption(findTabSelect());
  if (!tabRow) return;
  let tab = document.getElementById(TAB_ID);
  if (tab && tab.parentElement !== tabRow) { tab.remove(); tab = null; }
  if (!tab) {
    const sample = ["Instructions", "Configuration", "Runs", "Budget", "Dashboard"].map(findTabByLabel).find(Boolean);
    tab = Object.assign(document.createElement("button"), { id: TAB_ID, type: "button", textContent: "CLI", className: sample?.className || "" });
    tab.addEventListener("click", (event) => {
      event.preventDefault();
      history.pushState(null, "", `${window.location.pathname}${window.location.search}${CLI_HASH}`);
      requestRender();
    });
    tabRow.appendChild(tab);
  }
  tab.dataset.agentRoute = route;
  tab.dataset.active = cliTabActive() ? "true" : "false";
  tab.dataset.state = cliTabActive() ? "active" : "inactive";
  muteNativeTabs(cliTabActive());
}

function ensureBaseStyle() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `#${TAB_ID}{display:inline-flex;align-items:center;min-height:32px;color:hsl(var(--muted-foreground));text-decoration:none;border-bottom:2px solid transparent}#${TAB_ID}:hover{color:hsl(var(--foreground))}#${TAB_ID}[data-active="true"]{color:hsl(var(--foreground));border-bottom-color:currentColor}[data-yalru-native-tab-muted="true"]{color:hsl(var(--muted-foreground))!important;border-bottom-color:transparent!important}[data-yalru-native-tab-muted="true"]::after{opacity:0!important}@media (max-width:640px){#${PANEL_ID}{margin-bottom:96px!important}#${PANEL_ID} .yalru-pty-frame{height:38vh!important;min-height:280px!important}}`;
  document.head.appendChild(style);
}

function panelMarkup(context) {
  const agent = context.agent;
  const room = context.room || {};
  const roomLabel = room.identifier || room.issueId || "room pending";
  const discordSurfaces = Array.isArray(context.discordSurfaces) ? context.discordSurfaces : [];
  const privateControls = privateControlsMarkup(agent);
  return `<style>${panelCss()}</style>`
    + `<div class="yalru-cli-header"><div><div class="yalru-cli-eyebrow">Agent Terminal</div><h3>${escapeHtml(agent.name)}</h3></div><div class="yalru-cli-chip">${escapeHtml(agent.key)} · ${escapeHtml(agent.adapter)}</div></div>`
    + `<div class="yalru-cli-meta"><span>${escapeHtml(roomLabel)}</span><span>${escapeHtml(agent.role || "No role set")}</span></div>`
    + discordSurfacesMarkup(discordSurfaces)
    + privateControls;
}

function privateControlsMarkup(agent) {
  if (!canUsePrivateControls()) return "";
  const terminalMarkup = privateTerminalMarkup(agent);
  return `<details class="yalru-adapter-auth" open><summary>Adapter auth</summary><div class="yalru-adapter-row"><span>Adapter</span><strong>${escapeHtml(agent.adapter)}</strong></div><div class="yalru-cli-actions"><button type="button" data-action="adapter-status">Check adapter auth</button><button type="button" data-action="adapter-reconnect">Run reconnect in terminal</button></div><pre class="yalru-adapter-output" data-adapter-output aria-live="polite">Not checked yet. Status checks never read or print secret values.</pre></details>`
    + terminalMarkup
    + `<details class="yalru-cli-fallback"><summary>Command runner fallback</summary><div class="yalru-terminal-toolbar"><button type="button" data-action="terminal-start">Start</button><button type="button" data-action="terminal-refresh">Refresh</button><button type="button" data-action="terminal-clear">Clear</button><button type="button" data-action="terminal-restart">Restart</button><button type="button" data-action="status">Status</button></div><pre class="yalru-terminal-output" data-terminal-output aria-live="polite">Starting terminal...</pre><form class="yalru-terminal-input-row" data-terminal-form><span aria-hidden="true">$</span><input id="yalru-agent-terminal-input" data-terminal-input autocomplete="off" spellcheck="false" placeholder="pwd" /><button type="submit" class="primary">Run</button></form></details>`
    + `<details class="yalru-agent-message"><summary>Agent message</summary><label class="yalru-cli-label" for="yalru-agent-cli-message">Message</label><textarea id="yalru-agent-cli-message" class="yalru-cli-textarea" rows="4" placeholder="Work Packet, review request, CLI instruction"></textarea><div class="yalru-cli-actions"><button type="button" data-action="attach">Attach</button><button type="button" data-action="wake" class="primary">Send + Wake</button></div><pre class="yalru-cli-output" data-output aria-live="polite">Ready.</pre></details>`;
}
function discordSurfacesMarkup(surfaces) {
  if (!surfaces.length) return "";
  return `<section class="yalru-discord-surfaces" aria-label="Discord chat surfaces"><div class="yalru-discord-heading"><span>Discord chat surfaces</span><small>copy only · planned channel/thread</small></div><div class="yalru-discord-list">${surfaces.map(discordSurfaceRow).join("")}</div></section>`;
}

function discordSurfaceRow(surface) {
  const routeKey = String(surface.routeKey || "");
  const displayName = String(surface.displayName || routeKey);
  const status = String(surface.status || "unknown");
  const purpose = String(surface.purpose || "");
  const channel = String(surface.channel || (surface.name ? `#${surface.name}` : "planned channel/thread"));
  const surfaceState = String(surface.surfaceState || "planned channel/thread");
  const bridgeDisabled = surface.dangerousExecutionBridge === false ? "bridge disabled" : "bridge unavailable";
  const statusTone = status.includes("degraded") ? "degraded" : "ready";
  return `<div class="yalru-discord-row" data-status="${escapeHtml(statusTone)}"><div class="yalru-discord-main"><strong>${escapeHtml(displayName)}</strong><span>${escapeHtml(channel)} · ${escapeHtml(surfaceState)}</span><small>${escapeHtml(purpose)}</small></div><div class="yalru-discord-side"><span>${escapeHtml(status)}</span><small>${escapeHtml(bridgeDisabled)}</small><button type="button" data-discord-copy data-copy-value="${escapeHtml(channel)}">Copy</button></div></div>`;
}

function panelCss() {
  return `#${PANEL_ID}{margin:0 0 1.5rem;border:1px solid hsl(var(--border));border-radius:8px;background:hsl(var(--card));padding:16px;color:hsl(var(--foreground));box-shadow:0 8px 24px rgba(0,0,0,.16)}#${PANEL_ID}.yalru-cli-floating{position:fixed;right:24px;bottom:24px;z-index:60;width:min(760px,calc(100vw - 32px));margin:0}#${PANEL_ID} .yalru-cli-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}#${PANEL_ID} .yalru-cli-eyebrow{font-size:11px;color:hsl(var(--muted-foreground));font-weight:600;letter-spacing:0;text-transform:uppercase}#${PANEL_ID} h3{margin:2px 0 0;font-size:16px;line-height:1.3;font-weight:650}#${PANEL_ID} .yalru-cli-chip{font-size:11px;color:hsl(var(--muted-foreground));border:1px solid hsl(var(--border));border-radius:6px;padding:4px 6px;white-space:nowrap}#${PANEL_ID} .yalru-cli-meta{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 12px;color:hsl(var(--muted-foreground));font-size:12px}#${PANEL_ID} .yalru-pty-toolbar{display:flex;justify-content:flex-end;margin:0 0 8px}#${PANEL_ID} .yalru-pty-toolbar a{display:inline-flex;align-items:center;min-height:30px;border:1px solid hsl(var(--border));border-radius:6px;background:hsl(var(--background));color:hsl(var(--foreground));padding:6px 10px;font-size:12px;font-weight:600;text-decoration:none;transition:background-color .16s ease,border-color .16s ease,transform .16s ease}#${PANEL_ID} .yalru-pty-toolbar a:hover{background:hsl(var(--accent));border-color:hsl(var(--border))}#${PANEL_ID} .yalru-pty-toolbar a:active{transform:translateY(1px)}#${PANEL_ID} .yalru-pty-frame-wrap{margin-top:0;border:1px solid hsl(var(--border));border-radius:6px;overflow:hidden;background:#050505}#${PANEL_ID} .yalru-pty-frame{display:block;width:100%;height:min(58vh,560px);min-height:420px;border:0;background:#050505}#${PANEL_ID} .yalru-terminal-toolbar,#${PANEL_ID} .yalru-cli-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}#${PANEL_ID} button{border:1px solid hsl(var(--border));border-radius:6px;background:hsl(var(--background));color:hsl(var(--foreground));padding:7px 10px;font-size:12px;font-weight:600;cursor:pointer;transition:background-color .16s ease,border-color .16s ease,transform .16s ease}#${PANEL_ID} button:hover{background:hsl(var(--accent));border-color:hsl(var(--border))}#${PANEL_ID} button:active{transform:translateY(1px)}#${PANEL_ID} button.primary{background:hsl(var(--primary));border-color:hsl(var(--primary));color:hsl(var(--primary-foreground))}#${PANEL_ID} button:disabled{opacity:.6;cursor:not-allowed;transform:none}#${PANEL_ID} .yalru-terminal-output{box-sizing:border-box;width:100%;min-height:220px;max-height:38vh;overflow:auto;margin:12px 0 0;border:1px solid hsl(var(--border));border-radius:6px;background:#050505;padding:12px;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12px;line-height:1.45;color:#d8f5dd;white-space:pre-wrap}#${PANEL_ID} .yalru-terminal-input-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:8px;margin-top:8px;border:1px solid hsl(var(--border));border-radius:6px;background:hsl(var(--background));padding:8px}#${PANEL_ID} .yalru-terminal-input-row span{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;color:hsl(var(--muted-foreground))}#${PANEL_ID} .yalru-terminal-input-row input{min-width:0;border:0;background:transparent;color:hsl(var(--foreground));font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;outline:0}#${PANEL_ID} .yalru-discord-surfaces{margin-top:12px;border-top:1px solid hsl(var(--border));padding-top:10px}#${PANEL_ID} .yalru-discord-heading{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:8px}#${PANEL_ID} .yalru-discord-heading span{font-size:12px;font-weight:650}#${PANEL_ID} .yalru-discord-heading small{font-size:11px;color:hsl(var(--muted-foreground));line-height:1.35}#${PANEL_ID} .yalru-discord-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}#${PANEL_ID} .yalru-discord-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;border:1px solid hsl(var(--border));border-radius:6px;background:hsl(var(--background));padding:8px 10px;min-width:0}#${PANEL_ID} .yalru-discord-main,#${PANEL_ID} .yalru-discord-side{display:flex;flex-direction:column;gap:3px;min-width:0}#${PANEL_ID} .yalru-discord-main strong{font-size:12px;line-height:1.35;overflow-wrap:anywhere}#${PANEL_ID} .yalru-discord-main span,#${PANEL_ID} .yalru-discord-main small,#${PANEL_ID} .yalru-discord-side small{font-size:11px;line-height:1.35;color:hsl(var(--muted-foreground));overflow-wrap:anywhere;word-break:normal}#${PANEL_ID} .yalru-discord-side{align-items:flex-end;text-align:right}#${PANEL_ID} .yalru-discord-side span{font-size:11px;line-height:1.35;font-weight:650;color:hsl(var(--foreground));overflow-wrap:anywhere}#${PANEL_ID} .yalru-discord-row[data-status="degraded"] .yalru-discord-side span{color:hsl(var(--destructive))}#${PANEL_ID} .yalru-discord-side button{margin-top:2px;padding:5px 8px}#${PANEL_ID} .yalru-adapter-auth,#${PANEL_ID} .yalru-cli-fallback,#${PANEL_ID} .yalru-agent-message{margin-top:12px;border-top:1px solid hsl(var(--border));padding-top:10px}#${PANEL_ID} .yalru-adapter-auth summary,#${PANEL_ID} .yalru-cli-fallback summary,#${PANEL_ID} .yalru-agent-message summary{cursor:pointer;color:hsl(var(--muted-foreground));font-size:12px;font-weight:600}#${PANEL_ID} .yalru-adapter-row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:10px;border:1px solid hsl(var(--border));border-radius:6px;background:hsl(var(--background));padding:8px 10px;font-size:12px}#${PANEL_ID} .yalru-adapter-row span{color:hsl(var(--muted-foreground))}#${PANEL_ID} .yalru-adapter-row strong{font-weight:650;overflow-wrap:anywhere}#${PANEL_ID} .yalru-adapter-output{min-height:64px;max-height:240px;overflow:auto;margin:10px 0 0;border:1px solid hsl(var(--border));border-radius:6px;background:hsl(var(--background));padding:10px;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12px;line-height:1.45;color:hsl(var(--muted-foreground));white-space:pre-wrap}#${PANEL_ID} .yalru-cli-label{display:block;margin:10px 0 6px;font-size:12px;color:hsl(var(--muted-foreground));font-weight:600}#${PANEL_ID} .yalru-cli-textarea{box-sizing:border-box;width:100%;min-height:96px;resize:vertical;border:1px solid hsl(var(--border));border-radius:6px;background:hsl(var(--background));color:hsl(var(--foreground));padding:10px;font:inherit;line-height:1.45}#${PANEL_ID} .yalru-cli-textarea:focus{outline:2px solid hsl(var(--primary) / .45);outline-offset:1px}#${PANEL_ID} .yalru-cli-command{margin-top:10px;border:1px solid hsl(var(--border));border-radius:6px;background:hsl(var(--muted) / .35);padding:8px;overflow-x:auto;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12px;color:hsl(var(--muted-foreground));white-space:nowrap}#${PANEL_ID} .yalru-cli-output{min-height:48px;max-height:220px;overflow:auto;margin:12px 0 0;border:1px solid hsl(var(--border));border-radius:6px;background:hsl(var(--background));padding:10px;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12px;line-height:1.45;color:hsl(var(--muted-foreground));white-space:pre-wrap}@media (max-width:640px){#${PANEL_ID}{position:relative;z-index:2147483000!important;padding:12px}#${PANEL_ID} .yalru-cli-header{flex-direction:column}#${PANEL_ID} .yalru-cli-chip{white-space:normal}#${PANEL_ID} .yalru-pty-toolbar{justify-content:flex-start}#${PANEL_ID} .yalru-pty-frame-wrap{display:none}#${PANEL_ID} .yalru-pty-frame{height:52vh;min-height:340px}#${PANEL_ID} .yalru-terminal-output{min-height:200px;max-height:36vh}#${PANEL_ID} .yalru-discord-list{grid-template-columns:repeat(2,minmax(0,1fr))}#${PANEL_ID} .yalru-discord-row{grid-template-columns:1fr}#${PANEL_ID} .yalru-adapter-auth{margin-top:140px}#${PANEL_ID} .yalru-discord-main small{display:none}#${PANEL_ID} .yalru-discord-side{align-items:flex-start;text-align:left}}`;
}

function terminalFrameSrc(agentKey) {
  const route = TERMINAL_ROUTE_ALIASES[agentKey] || agentKey;
  return `/yalru-terminal/${encodeURIComponent(route)}/`;
}

function privateTerminalMarkup(agent) {
  if (!canUsePrivateControls()) return "";
  const terminalHref = terminalFrameSrc(agent.key);
  return `<div class="yalru-pty-toolbar"><a href="${terminalHref}" target="_blank" rel="noreferrer">Open full terminal</a></div><div class="yalru-pty-frame-wrap"><iframe class="yalru-pty-frame" src="${terminalHref}" title="${escapeHtml(agent.name)} real terminal"></iframe></div>`;
}

function canUsePrivateControls() {
  const host = window.location.hostname;
  return host === "localhost" || host === "127.0.0.1" || host === "::1" || host.endsWith(".localhost");
}

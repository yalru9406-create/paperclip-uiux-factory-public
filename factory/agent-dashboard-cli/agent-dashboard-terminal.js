async function startTerminal(route) {
  await postTerminal("/api/terminal/start", { agentRoute: route }, "Starting terminal...");
}

async function refreshTerminal(route, quiet = false) {
  await getTerminal(`/api/terminal/output?agentRoute=${encodeURIComponent(route)}`, quiet ? "" : "Refreshing terminal...", quiet);
}

async function clearTerminal(route) {
  await postTerminal("/api/terminal/clear", { agentRoute: route }, "Clearing terminal...");
}

async function restartTerminal(route) {
  await postTerminal("/api/terminal/restart", { agentRoute: route }, "Restarting terminal...");
}

async function sendTerminalInput(route) {
  const input = document.querySelector(`#${PANEL_ID} [data-terminal-input]`);
  const value = input?.value || "";
  if (input) input.value = "";
  await postTerminal("/api/terminal/input", { agentRoute: route, input: value }, value || "Sending Enter...");
}

function startTerminalPoll(route) {
  stopTerminalPoll();
  terminalPollTimer = window.setInterval(() => {
    const panel = document.getElementById(PANEL_ID);
    if (!panel || panel.dataset.agentRoute !== route || !cliTabActive()) {
      stopTerminalPoll();
      return;
    }
    refreshTerminal(route, true);
  }, 2500);
}

function stopTerminalPoll() {
  if (!terminalPollTimer) return;
  window.clearInterval(terminalPollTimer);
  terminalPollTimer = 0;
}

async function sendMessage(route, wake) {
  const panel = document.getElementById(PANEL_ID);
  const textarea = panel?.querySelector("#yalru-agent-cli-message");
  const message = (textarea?.value || "").trim();
  if (!message) {
    writeOutput("Message is required.");
    return;
  }
  await postJson("/api/chat", { agentRoute: route, message, wake }, wake ? "Sending and waking..." : "Attaching...");
}

async function loadStatus(route) {
  await getJson(`/api/status?agentRoute=${encodeURIComponent(route)}`, "Loading status...");
}

async function loadAdapterStatus(route) {
  await getAdapterJson(`/api/adapter/status?agentRoute=${encodeURIComponent(route)}`, "Checking adapter auth...");
}

async function runAdapterReconnect(route) {
  setBusy(true);
  writeAdapter("Sending reconnect command to this agent terminal...");
  try {
    const response = await fetch(`${API_BASE}/api/adapter/reconnect`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ agentRoute: route }),
    });
    const text = await formatTerminalResponse(response);
    writeTerminal(text);
    writeAdapter(response.ok ? "Reconnect command was sent to the terminal." : text);
  } catch (error) {
    writeAdapter(error instanceof Error ? error.message : "Request failed.");
  } finally {
    setBusy(false);
  }
}

async function postJson(path, payload, pendingText) {
  setBusy(true);
  writeOutput(pendingText);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    writeOutput(await formatResponse(response));
  } catch (error) {
    writeOutput(error instanceof Error ? error.message : "Request failed.");
  } finally {
    setBusy(false);
  }
}

async function getJson(path, pendingText) {
  setBusy(true);
  writeOutput(pendingText);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    writeOutput(await formatResponse(response));
  } catch (error) {
    writeOutput(error instanceof Error ? error.message : "Request failed.");
  } finally {
    setBusy(false);
  }
}

async function getAdapterJson(path, pendingText) {
  setBusy(true);
  writeAdapter(pendingText);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    writeAdapter(await formatAdapterResponse(response));
  } catch (error) {
    writeAdapter(error instanceof Error ? error.message : "Request failed.");
  } finally {
    setBusy(false);
  }
}

async function postTerminal(path, payload, pendingText) {
  setBusy(true);
  writeTerminal(pendingText);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    writeTerminal(await formatTerminalResponse(response));
  } catch (error) {
    writeTerminal(error instanceof Error ? error.message : "Request failed.");
  } finally {
    setBusy(false);
  }
}

async function getTerminal(path, pendingText, quiet) {
  if (!quiet) {
    setBusy(true);
    writeTerminal(pendingText);
  }
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    writeTerminal(await formatTerminalResponse(response));
  } catch (error) {
    if (!quiet) writeTerminal(error instanceof Error ? error.message : "Request failed.");
  } finally {
    if (!quiet) setBusy(false);
  }
}

async function formatResponse(response) {
  const data = await response.json();
  if (typeof data.stdout === "string" && data.stdout.trim().startsWith("{")) {
    try {
      data.stdoutJson = JSON.parse(data.stdout);
      delete data.stdout;
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
    }
  }
  return JSON.stringify(data, null, 2);
}

async function formatTerminalResponse(response) {
  const data = await response.json();
  const stdout = typeof data.stdout === "string" ? data.stdout : "";
  const stderr = typeof data.stderr === "string" ? data.stderr : "";
  if (response.ok && stdout) return stdout;
  if (stdout || stderr) return [stdout, stderr].filter(Boolean).join("\n");
  return JSON.stringify(data, null, 2);
}

async function formatAdapterResponse(response) {
  const data = await response.json();
  if (!response.ok || !data.adapter) return JSON.stringify(data, null, 2);
  const adapter = data.adapter;
  const lines = [
    `${adapter.provider || data.agent?.adapter || "Adapter"}: ${adapter.state || "unknown"}`,
    adapter.summary ? `Summary: ${adapter.summary}` : "",
    adapter.geminiCli ? `Gemini CLI: ${adapter.geminiCli.state || "unknown"} - ${adapter.geminiCli.summary || ""}` : "",
    adapter.reconnectCommand ? `Reconnect: ${adapter.reconnectCommand}` : "",
  ];
  const evidence = Array.isArray(adapter.evidence) ? adapter.evidence.map(formatEvidence).filter(Boolean) : [];
  if (evidence.length) lines.push("Evidence:", ...evidence.map((item) => `- ${item}`));
  return lines.filter(Boolean).join("\n");
}

function formatEvidence(item) {
  if (!item || typeof item !== "object") return "";
  const name = item.name || "item";
  if ("exists" in item) return `${name}: ${item.exists ? "exists" : "missing"}${item.path ? ` (${item.path})` : ""}`;
  if ("installed" in item) return `${name}: ${item.installed ? "installed" : "missing"}${item.path ? ` (${item.path})` : ""}`;
  return "";
}

function setBusy(busy) {
  document.querySelectorAll(`#${PANEL_ID} button`).forEach((button) => { button.disabled = busy; });
}

function writeOutput(text) {
  const output = document.querySelector(`#${PANEL_ID} [data-output]`); if (output) output.textContent = text;
}

function writeAdapter(text) {
  const output = document.querySelector(`#${PANEL_ID} [data-adapter-output]`);
  if (!output) return;
  output.textContent = text;
}

function writeTerminal(text) {
  const output = document.querySelector(`#${PANEL_ID} [data-terminal-output]`);
  if (!output) return;
  output.textContent = text;
  output.scrollTop = output.scrollHeight;
}

async function copyDiscordSurface(event) {
  const button = event.currentTarget;
  const channel = button?.dataset.copyValue || "";
  try {
    await navigator.clipboard.writeText(channel);
    const previous = button.textContent;
    button.textContent = "Copied";
    window.setTimeout(() => { button.textContent = previous || "Copy"; }, 1200);
  } catch (error) {
    writeOutput(error instanceof Error ? error.message : channel);
  }
}

function escapeHtml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

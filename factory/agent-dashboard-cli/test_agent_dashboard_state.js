const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "agent-dashboard-state.js"), "utf8");
const sandbox = {
  window: {
    clearTimeout() {},
    setTimeout() {},
    location: { pathname: "/YAL/agents/hermes-top-orchestrator/dashboard", search: "", hash: "", hostname: "paperclip.example.test" },
  },
  document: {
    querySelector() { return null; },
    querySelectorAll() { return []; },
    createElement() { return { dataset: {}, addEventListener() {} }; },
    body: { appendChild() {} },
  },
  history: {
    pushState() {},
    replaceState() {},
  },
  MutationObserver: function MutationObserver() {
    return { observe() {} };
  },
  fetch() {},
  escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },
  console,
};

vm.createContext(sandbox);
vm.runInContext(`${source}\nthis.discordSurfacesHeading = discordSurfacesHeading;\nthis.panelMarkup = panelMarkup;`, sandbox);

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${expected}, got ${actual}`);
  }
}

function assertContains(actual, expected, message) {
  if (!actual.includes(expected)) {
    throw new Error(`${message}: expected markup to contain ${expected}`);
  }
}

function assertNotContains(actual, expected, message) {
  if (actual.includes(expected)) {
    throw new Error(`${message}: expected markup not to contain ${expected}`);
  }
}

assertEqual(
  sandbox.discordSurfacesHeading([{ surfaceState: "created_channel_verified" }]),
  "copy only · verified channels",
  "exact verified state should show verified heading",
);
assertEqual(
  sandbox.discordSurfacesHeading([{ surfaceState: "unverified" }]),
  "copy only · planned channel/thread",
  "unverified state must not show verified heading",
);
assertEqual(
  sandbox.discordSurfacesHeading([
    { surfaceState: "created_channel_verified" },
    { surfaceState: "not_verified" },
  ]),
  "copy only · planned channel/thread",
  "mixed states must not show verified heading",
);

const publicMarkup = sandbox.panelMarkup({
  agent: {
    key: "hermes-top-orchestrator",
    name: "Hermes",
    adapter: "hermes_local",
    role: "orchestrator",
  },
  room: { identifier: "YAL-public" },
  discordSurfaces: [],
  opsStatus: {
    tanLive: {
      services: [{ name: "tan-live", state: "active" }],
      tanMutation: "not_performed",
      liveMutationLock: "C5 locked: no live orders, positions, exchange configuration, or service mutation.",
    },
    paperArtifacts: {
      policy: "metadata_only",
      latestRunPresent: true,
      artifactCount: 2,
      totalBytes: 2048,
      newestModifiedAt: "2026-06-20T12:00:00+00:00",
      artifacts: [
        { name: "paper_report.json", exists: true },
        { name: "paper_research_gate_latest.txt", exists: true },
        { name: "promotion_bundle.json", exists: false },
      ],
      promotionGate: {
        promotionBundleStatus: "MISSING",
        paperGateVerdict: "RESEARCH_ONLY",
        liveApprovalState: "NONE",
      },
      rawContents: "not_exposed",
    },
    vpsQa: {
      privateTerminalEndpoints: "not_exposed_public",
      safetyFacts: ["systemctl is-active whitelist only", "raw paper report contents not exposed"],
    },
  },
});

assertContains(publicMarkup, "Public ops status", "public panel should expose read-only ops heading");
assertContains(publicMarkup, "TAN LIVE", "public panel should expose TAN LIVE service visibility");
assertContains(publicMarkup, "tan_mutation=not_performed", "public panel should expose mutation safety fact");
assertContains(publicMarkup, "Live mutation locked / C5", "public panel should expose C5 lock wording");
assertContains(publicMarkup, "PAPER latest artifacts", "public panel should expose paper artifact metadata");
assertContains(publicMarkup, "paper_report.json:ok", "public panel should prioritize paper report metadata");
assertContains(publicMarkup, "promotion_bundle.json:missing", "public panel should surface missing promotion evidence");
assertContains(publicMarkup, "promotion MISSING", "public panel should expose promotion gate state");
assertContains(publicMarkup, "live NONE", "public panel should expose live approval state");
assertContains(publicMarkup, "VPS QA safety", "public panel should expose QA safety facts");
assertNotContains(publicMarkup, "Open full terminal", "public panel must not expose terminal links");
assertNotContains(publicMarkup, "Command runner fallback", "public panel must not expose command runner");
assertNotContains(publicMarkup, "Agent message", "public panel must not expose message controls");

console.log(JSON.stringify({ ok: true, assertions: 12 }));

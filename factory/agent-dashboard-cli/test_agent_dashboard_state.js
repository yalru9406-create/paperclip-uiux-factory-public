const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "agent-dashboard-state.js"), "utf8");
const sandbox = {
  window: {
    clearTimeout() {},
    setTimeout() {},
    location: { pathname: "/YAL/agents/hermes-top-orchestrator/dashboard", search: "", hash: "" },
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
  console,
};

vm.createContext(sandbox);
vm.runInContext(`${source}\nthis.discordSurfacesHeading = discordSurfacesHeading;`, sandbox);

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${expected}, got ${actual}`);
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

console.log(JSON.stringify({ ok: true, assertions: 3 }));

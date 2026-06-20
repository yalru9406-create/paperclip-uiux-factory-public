(function () {
  const routeAliases = {
    antigravity: "gemini-antigravity-lane",
    freeclaude: "freeclaude-glm-5-2-critic",
    gajecode: "gajecode-glm-5-2-engineer",
    hermes: "hermes-top-orchestrator",
    lazycodex: "lazycodex-gpt-lane",
    qa: "vps-qa-harness-glm",
  };

  function slugifyRoute(value) {
    const slug = decodeURIComponent(value)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return slug || "agent";
  }

  function redirectAliasRoute() {
    const match = window.location.pathname.match(/^(.*\/agents\/)([^/?#]+)(.*)$/);
    if (!match) return false;
    const canonical = routeAliases[slugifyRoute(match[2])];
    if (!canonical) return false;
    const suffix = match[3] || "/dashboard";
    const targetPath = `${match[1]}${canonical}${suffix}`;
    const targetUrl = `${targetPath}${window.location.search}${window.location.hash}`;
    window.location.replace(targetUrl);
    return true;
  }

  if (redirectAliasRoute()) return;

  const status = window.YalruAgentDashboardStatus;
  if (status === "loading" || status === "loaded") return;
  window.YalruAgentDashboardStatus = "loading";
  const basePath = "/yalru-agent-cli/";
  const scripts = [
    "agent-dashboard-state.js",
    "agent-dashboard-dom.js",
    "agent-dashboard-terminal.js",
    "agent-dashboard-bootstrap.js",
  ];

  function loadScript(index) {
    if (index >= scripts.length) {
      window.YalruAgentDashboardStatus = "loaded";
      return;
    }
    const script = document.createElement("script");
    script.src = basePath + scripts[index];
    script.async = false;
    script.onload = () => loadScript(index + 1);
    script.onerror = () => {
      window.YalruAgentDashboardStatus = "failed";
    };
    document.head.appendChild(script);
  }

  loadScript(0);
})();

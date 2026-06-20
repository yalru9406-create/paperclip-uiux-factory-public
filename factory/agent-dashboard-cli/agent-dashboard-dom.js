function placePanel(panel) {
  const tabRow = findTabRow();
  if (tabRow && tabRow.parentElement) {
    tabRow.parentElement.insertBefore(panel, tabRow.nextSibling);
    panel.classList.remove("yalru-cli-floating");
    return;
  }
  const tabSelect = findTabSelect();
  if (tabSelect && tabSelect.parentElement) {
    tabSelect.parentElement.insertBefore(panel, tabSelect.nextSibling);
    panel.classList.remove("yalru-cli-floating");
    return;
  }
  const anchor = findTextElement(["Latest Run", "Live Run", "Recent Tasks"]);
  const container = anchor ? nearestDashboardBlock(anchor) : null;
  if (container && container.parentElement) {
    container.parentElement.insertBefore(panel, container);
    panel.classList.remove("yalru-cli-floating");
    return;
  }
  const main = document.querySelector("main") || document.querySelector("#root");
  if (main) {
    main.prepend(panel);
    return;
  }
  panel.classList.add("yalru-cli-floating");
  document.body.appendChild(panel);
}

function findTextElement(labels) {
  const elements = Array.from(document.querySelectorAll("h1,h2,h3,h4,span,a,div"));
  return elements.find((element) => labels.includes((element.textContent || "").trim())) || null;
}

function findTabByLabel(label) {
  const scope = document.querySelector("main#main-content") || document.querySelector("main") || document;
  return Array.from(scope.querySelectorAll("button,a")).find((element) => (element.textContent || "").trim() === label) || null;
}

function findTabSelect() {
  const scope = document.querySelector("main#main-content") || document.querySelector("main") || document;
  return Array.from(scope.querySelectorAll("select")).find((select) => Array.from(select.options).some((option) => option.value === "skills")) || null;
}

function ensureSelectOption(select) {
  if (!select) return;
  if (!Array.from(select.options).some((option) => option.value === CLI_VALUE)) {
    select.appendChild(Object.assign(document.createElement("option"), { value: CLI_VALUE, textContent: "CLI" }));
  }
  if (cliTabActive()) select.value = CLI_VALUE;
  if (select.dataset.yalruCliBound === "true") return;
  select.dataset.yalruCliBound = "true";
  select.addEventListener("change", (event) => {
    if (select.value !== CLI_VALUE) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    history.pushState(null, "", `${window.location.pathname}${window.location.search}${CLI_HASH}`);
    requestRender();
  }, true);
}

function findTabRow() {
  const labels = ["Dashboard", "Instructions", "Skills", "Configuration", "Runs", "Budget"];
  const tabs = labels.map(findTabByLabel).filter(Boolean);
  if (tabs.length < 2) return null;
  let candidate = tabs[0].parentElement;
  for (let depth = 0; candidate && depth < 4; depth += 1) {
    if (tabs.every((tab) => candidate.contains(tab))) return candidate;
    candidate = candidate.parentElement;
  }
  return tabs[0].parentElement;
}

function muteNativeTabs(muted) {
  ["Dashboard", "Instructions", "Skills", "Configuration", "Runs", "Budget"].map(findTabByLabel).filter(Boolean).forEach((tab) => {
    tab.dataset.yalruNativeTabMuted = muted ? "true" : "false";
  });
}

function nearestDashboardBlock(element) {
  let node = element;
  for (let depth = 0; node && depth < 5; depth += 1) {
    if (node.parentElement && node.parentElement.children.length > 1) return node.parentElement;
    node = node.parentElement;
  }
  return element.parentElement;
}

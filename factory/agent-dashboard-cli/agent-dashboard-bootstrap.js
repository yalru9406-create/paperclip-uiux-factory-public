if (window.YalruAgentDashboardBootstrapped !== true) {
  window.YalruAgentDashboardBootstrapped = true;
  const observer = new MutationObserver(requestRender);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("popstate", requestRender);
  const originalPushState = history.pushState;
  history.pushState = function pushState() {
    originalPushState.apply(this, arguments);
    requestRender();
  };
  const originalReplaceState = history.replaceState;
  history.replaceState = function replaceState() {
    originalReplaceState.apply(this, arguments);
    requestRender();
  };
  requestRender();
}

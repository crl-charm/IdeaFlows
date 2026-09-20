(function () {
  "use strict";

  if (!("serviceWorker" in navigator)) return;

  let hasUnsavedChanges = false;
  let waitingWorker = null;
  let updateRequested = false;
  let reloadStarted = false;
  let notice = null;

  function markDirty(event) {
    if (event.target.closest && event.target.closest("form")) {
      hasUnsavedChanges = true;
    }
  }

  document.addEventListener("input", markDirty, true);
  document.addEventListener("change", markDirty, true);

  function showUpdate(worker) {
    waitingWorker = worker;
    if (!notice) notice = createUpdateNotice();
    notice.hidden = false;
  }

  function createUpdateNotice() {
    const panel = document.createElement("aside");
    const message = document.createElement("p");
    const actions = document.createElement("div");
    const updateButton = document.createElement("button");
    const laterButton = document.createElement("button");

    panel.className = "pwa-update";
    panel.hidden = true;
    panel.setAttribute("role", "region");
    panel.setAttribute("aria-label", "IdeaFlow update available");
    message.textContent = "A new IdeaFlow version is ready. Finish any active order, report, or form before updating.";
    message.setAttribute("aria-live", "polite");
    actions.className = "pwa-update-actions";
    updateButton.type = "button";
    updateButton.className = "pwa-update-now";
    updateButton.textContent = "Update now";
    laterButton.type = "button";
    laterButton.textContent = "Later";

    updateButton.addEventListener("click", function () {
      if (hasUnsavedChanges && !window.confirm(
        "You have unsaved changes. Update and reload anyway?"
      )) return;
      if (!waitingWorker) return;
      updateRequested = true;
      updateButton.disabled = true;
      updateButton.textContent = "Updating…";
      waitingWorker.postMessage({ type: "SKIP_WAITING" });
    });
    laterButton.addEventListener("click", function () {
      panel.hidden = true;
    });

    actions.append(updateButton, laterButton);
    panel.append(message, actions);
    document.body.append(panel);
    return panel;
  }

  navigator.serviceWorker.addEventListener("controllerchange", function () {
    if (!updateRequested || reloadStarted) return;
    reloadStarted = true;
    const now = Date.now();
    try {
      const lastReload = Number(sessionStorage.getItem("ideaflow-sw-reload")) || 0;
      if (now - lastReload < 10000) return;
      sessionStorage.setItem("ideaflow-sw-reload", String(now));
    } catch (_) {}
    window.location.reload();
  });

  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(function (registration) {
      if (registration.waiting) showUpdate(registration.waiting);
      registration.addEventListener("updatefound", function () {
        const installing = registration.installing;
        if (!installing) return;
        installing.addEventListener("statechange", function () {
          if (installing.state === "installed" && navigator.serviceWorker.controller) {
            showUpdate(installing);
          }
        });
      });
    }).catch(function () {
      console.warn("IdeaFlow service worker registration failed.");
    });
  });
})();

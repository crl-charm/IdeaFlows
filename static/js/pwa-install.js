(function () {
  "use strict";

  const root = document.querySelector("[data-pwa-install]");
  if (!root) return;

  const button = root.querySelector("[data-pwa-install-button]");
  const label = button.querySelector("span");
  const status = root.querySelector("[data-pwa-install-status]");
  const instructions = document.querySelector("[data-pwa-ios-instructions]");
  const closeButton = instructions && instructions.querySelector("[data-pwa-close]");
  const userAgent = navigator.userAgent;
  const isIOS = /iPad|iPhone|iPod/.test(userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isSafari = /Safari/.test(userAgent) && !/(CriOS|FxiOS|EdgiOS|OPiOS)/.test(userAgent);
  const isInstalled = window.matchMedia("(display-mode: standalone)").matches ||
    navigator.standalone === true;
  let installPrompt = null;

  if (isInstalled) return;

  function showInstaller(text) {
    label.textContent = text;
    root.hidden = false;
  }

  if (isIOS && isSafari) {
    showInstaller("Add IdeaFlow to Home Screen");
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    installPrompt = event;
    showInstaller("Install IdeaFlow");
  });

  button.addEventListener("click", async function () {
    if (installPrompt) {
      button.disabled = true;
      await installPrompt.prompt();
      const choice = await installPrompt.userChoice;
      status.textContent = choice.outcome === "accepted"
        ? "Installation started."
        : "Installation cancelled.";
      if (choice.outcome === "dismissed") {
        try { localStorage.setItem("ideaflow-install-dismissed", "true"); } catch (_) {}
      }
      installPrompt = null;
      root.hidden = true;
      button.disabled = false;
      return;
    }

    if (isIOS && isSafari && instructions) {
      if (typeof instructions.showModal === "function") instructions.showModal();
      else instructions.setAttribute("open", "");
    }
  });

  if (closeButton) {
    closeButton.addEventListener("click", function () {
      if (typeof instructions.close !== "function") instructions.removeAttribute("open");
    });
  }

  window.addEventListener("appinstalled", function () {
    installPrompt = null;
    button.hidden = true;
    root.hidden = false;
    status.textContent = "IdeaFlow was installed successfully.";
    try { localStorage.removeItem("ideaflow-install-dismissed"); } catch (_) {}
    window.setTimeout(function () { root.hidden = true; }, 4000);
  });
})();

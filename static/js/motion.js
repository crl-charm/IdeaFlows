/* Shared navigation feedback. Full page navigation remains intentionally native. */
(function enableIdeaFlowMotion() {
  "use strict";

  var root = document.documentElement;
  var skeletonStart = window.performance && window.performance.now
    ? window.performance.now()
    : 0;
  var skeletonFinished = false;

  function revealContent() {
    if (skeletonFinished) return;
    var elapsed = window.performance && window.performance.now
      ? window.performance.now() - skeletonStart
      : 180;
    var remaining = Math.max(0, 180 - elapsed);

    window.setTimeout(function () {
      if (skeletonFinished) return;
      skeletonFinished = true;
      root.classList.add("ih-content-ready");
    }, remaining);
  }

  function isModifiedClick(event) {
    return event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
  }

  function navigationUrl(target) {
    var link = target && target.closest ? target.closest("a[href]") : null;
    if (link) {
      if (link.target && link.target !== "_self") return null;
      if (link.hasAttribute("download")) return null;
      var rawHref = link.getAttribute("href") || "";
      if (!rawHref || rawHref.charAt(0) === "#" || rawHref.indexOf("javascript:") === 0) return null;
      var parsed = new URL(link.href, window.location.href);
      return parsed.origin === window.location.origin ? parsed : null;
    }

    var button = target && target.closest
      ? target.closest("[data-href], [onclick*='location.href']")
      : null;
    if (!button) return null;
    var candidate = button.getAttribute("data-href") || button.getAttribute("onclick") || "";
    var match = candidate.match(/(?:window\.)?location\.href\s*=\s*['\"]([^'\"]+)['\"]/);
    if (!match && button.hasAttribute("data-href")) match = [candidate, candidate];
    if (!match) return null;
    var buttonUrl = new URL(match[1], window.location.href);
    return buttonUrl.origin === window.location.origin ? buttonUrl : null;
  }

  function beginNavigation() {
    root.classList.add("ih-navigating");
  }

  function resetNavigation(event) {
    root.classList.remove("ih-navigating");
    root.classList.toggle("ih-restored", Boolean(event && event.persisted));
  }

  document.addEventListener("click", function (event) {
    if (event.defaultPrevented || isModifiedClick(event)) return;
    var destination = navigationUrl(event.target);
    if (!destination) return;
    if (destination.href === window.location.href) return;
    beginNavigation();
  }, true);

  window.addEventListener("beforeunload", beginNavigation);
  window.addEventListener("pageshow", resetNavigation);
  window.addEventListener("load", revealContent, { once: true });
  window.setTimeout(revealContent, 1500);

  if (document.readyState === "complete") revealContent();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      window.requestAnimationFrame(function () { root.classList.add("ih-motion-ready"); });
    }, { once: true });
  } else {
    window.requestAnimationFrame(function () { root.classList.add("ih-motion-ready"); });
  }
})();

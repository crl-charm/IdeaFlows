(() => {
  'use strict';
  const modal = document.getElementById('systemUpdatesModal');
  if (!modal || modal.dataset.updatesBound) return;
  modal.dataset.updatesBound = 'true';
  const dot = document.getElementById('systemUpdatesDot');
  const status = document.getElementById('systemUpdatesStatus');
  const showAll = document.getElementById('systemUpdatesShowAll');
  const patches = [...modal.querySelectorAll('[data-update-patch]')];
  const ids = [...modal.querySelectorAll('[data-update-id]')].map(entry => entry.dataset.updateId);
  const latestIds = [...patches[0].querySelectorAll('[data-update-id]')].map(entry => entry.dataset.updateId);
  const key = modal.dataset.readKey;
  let remembered = new Set();

  function seenIds() {
    const seen = new Set(remembered);
    try {
      const saved = JSON.parse(localStorage.getItem(key) || '[]');
      if (Array.isArray(saved)) saved.forEach(id => { if (typeof id === 'string') seen.add(id); });
    } catch (_) { /* Reading updates still works when storage is unavailable. */ }
    return seen;
  }

  function refreshDot() {
    const seen = seenIds();
    const unread = latestIds.some(id => !seen.has(id));
    dot.hidden = !unread;
    status.textContent = unread ? 'New patch notes available.' : 'Latest patch notes read.';
  }

  function markSeen(visibleIds) {
    remembered = seenIds();
    visibleIds.forEach(id => remembered.add(id));
    try { localStorage.setItem(key, JSON.stringify([...remembered])); } catch (_) {}
    refreshDot();
  }

  function showHistory(expanded) {
    patches.slice(1).forEach(patch => { patch.hidden = !expanded; });
    if (showAll) {
      showAll.setAttribute('aria-expanded', String(expanded));
      showAll.textContent = expanded ? 'Show latest only' : 'Show All';
    }
  }

  modal.addEventListener('show.bs.modal', () => showHistory(false));
  modal.addEventListener('shown.bs.modal', () => markSeen(latestIds));
  showAll?.addEventListener('click', () => {
    const expanded = showAll.getAttribute('aria-expanded') !== 'true';
    showHistory(expanded);
    if (expanded) markSeen(ids);
  });
  modal.addEventListener('click', event => {
    if (event.target.closest('.system-update-link')) window.bootstrap.Modal.getInstance(modal)?.hide();
  });
  window.addEventListener('pageshow', refreshDot);
  window.addEventListener('storage', event => { if (event.key === key || event.key === null) refreshDot(); });
  refreshDot();
})();

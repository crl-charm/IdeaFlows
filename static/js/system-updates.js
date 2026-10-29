(() => {
  'use strict';
  const modal = document.getElementById('systemUpdatesModal');
  if (!modal || modal.dataset.updatesBound) return;
  modal.dataset.updatesBound = 'true';
  const dot = document.getElementById('systemUpdatesDot');
  const status = document.getElementById('systemUpdatesStatus');
  const ids = [...modal.querySelectorAll('[data-update-id]')].map(entry => entry.dataset.updateId);
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
    const unread = ids.some(id => !seen.has(id));
    dot.hidden = !unread;
    status.textContent = unread ? 'New system updates available.' : 'System updates are up to date.';
  }

  modal.addEventListener('shown.bs.modal', () => {
    remembered = seenIds();
    ids.forEach(id => remembered.add(id));
    try { localStorage.setItem(key, JSON.stringify([...remembered])); } catch (_) {}
    refreshDot();
  });
  modal.addEventListener('click', event => {
    if (event.target.closest('.system-update-link')) window.bootstrap.Modal.getInstance(modal)?.hide();
  });
  window.addEventListener('pageshow', refreshDot);
  window.addEventListener('storage', event => { if (event.key === key || event.key === null) refreshDot(); });
  refreshDot();
})();

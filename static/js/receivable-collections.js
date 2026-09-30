(() => {
  const methods = [['cash', 'Cash'], ['gcash', 'GCash'], ['bdo', 'BDO'],
    ['bpi', 'BPI'], ['queenbank', 'QueenBank'], ['unclassified', 'Legacy / unknown']];
  let requestId = 0;

  function todayInManila() {
    return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  }

  async function refresh() {
    const currentRequest = ++requestId;
    const container = document.getElementById('receivable-method-cards');
    const params = new URLSearchParams();
    const start = document.getElementById('collectionStartDate').value;
    const end = document.getElementById('collectionEndDate').value;
    if (start) params.set('start_date', start);
    if (end) params.set('end_date', end);
    try {
      const response = await fetch(`${window.managementBase}/daily-balance/api/reports?${params}`, { credentials: 'include' });
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Collections unavailable');
      const result = await response.json();
      if (!result.success || !Array.isArray(result.data)) throw new Error('Collections unavailable');
      if (currentRequest !== requestId) return;

      const totals = Object.fromEntries(methods.map(([key]) => [key, 0]));
      result.data.forEach(report => methods.forEach(([key]) => {
        totals[key] += Number((report.collection_methods || {})[key] || 0);
      }));
      const all = Object.values(totals).reduce((sum, amount) => sum + amount, 0);
      const card = (label, amount) => `<div class="col-12 col-sm-6 col-xl-3"><div class="card h-100 shadow-sm"><div class="card-body"><div class="small text-muted fw-semibold">${label} · collected</div><div class="h5 mb-0">₱${amount.toFixed(2)}</div></div></div></div>`;
      container.innerHTML = card('All methods', all) + methods
        .filter(([key]) => key !== 'unclassified' || totals[key])
        .map(([key, label]) => card(label, totals[key])).join('');
    } catch (_) {
      if (currentRequest === requestId) container.textContent = 'Could not load collection totals. Please retry.';
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const start = document.getElementById('collectionStartDate');
    const end = document.getElementById('collectionEndDate');
    if (!start || !end) return;
    start.value = end.value = todayInManila();
    start.addEventListener('change', refresh);
    end.addEventListener('change', refresh);
    document.getElementById('collectionToday').addEventListener('click', () => {
      start.value = end.value = todayInManila();
      refresh();
    });
    document.getElementById('collectionAll').addEventListener('click', () => {
      start.value = end.value = '';
      refresh();
    });
    window.refreshReceivableCollections = refresh;
    const socket = window.getIdeaFlowSocket?.();
    if (socket) socket.on('daily_balance_update', window.createDebouncedRefresh(refresh, 150));
    refresh();
  });
})();

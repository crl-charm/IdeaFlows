(() => {
  const errorBox = document.getElementById('statement-error');
  const reportError = error => { errorBox.textContent = error.message; errorBox.classList.remove('d-none'); errorBox.scrollIntoView({ block: 'center' }); };
  const form = document.getElementById('confirm-customer-history');
  async function associate(button, payload) {
    button.disabled = true;
    try {
      const response = await window.csrfFetch(`/admin/reports/api/accounts/${form.dataset.accountId}/review`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (response.status === 401) location.assign('/login');
      if (!response.ok || !result.success) throw new Error(result.error || 'Could not save history review.');
      location.reload();
    } catch (error) { reportError(error); button.disabled = false; }
  }
  form?.addEventListener('submit', event => {
    event.preventDefault();
    if (form.reportValidity()) associate(form.querySelector('button'), { action: 'confirm', confirmed: true });
  });
  for (const button of document.querySelectorAll('[data-associate-tab],[data-associate-debt]')) {
    button.addEventListener('click', () => associate(button, {
      action: 'associate', tab_id: button.dataset.associateTab, receivable_id: button.dataset.associateDebt
    }));
  }
  document.querySelectorAll('#export-customer-statement,[data-report-download]').forEach(button => button.addEventListener('click', async event => {
    const button = event.currentTarget;
    if (button.disabled) return;
    button.disabled = true;
    try {
      const response = await fetch(button.dataset.url, { credentials: 'same-origin', headers: { Accept: 'application/pdf' } });
      if (response.status === 401) location.assign('/login');
      if (!response.ok || !response.headers.get('content-type')?.includes('application/pdf')) {
        const result = response.headers.get('content-type')?.includes('application/json') ? await response.json() : {};
        throw new Error(result.error || 'Could not download the report. Please retry.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = response.headers.get('content-disposition')?.match(/filename="?([^";]+)/)?.[1] || 'IdeaFlow-Report.pdf';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (error) { reportError(error); }
    finally { button.disabled = false; }
  }));
})();

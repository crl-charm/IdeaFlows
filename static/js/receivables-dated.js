(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const pesos = value => `₱${Number(value || 0).toFixed(2)}`;
  const today = () => new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit'
  }).format(new Date());
  const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(`${value}T00:00:00Z`)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
  const normName = value => String(value || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();
  const normContact = value => String(value || '').replace(/\s+/g, '').toLocaleLowerCase();

  window.ReceivablesDatedPage = base => {
    const $ = id => document.getElementById(id);
    const state = { date: null, search: '', status: '', recordPage: 1, tabPage: 1,
      sequence: 0, suggestionSequence: 0, suggestions: [], selectedCustomer: null,
      tabs: [], records: [], detail: null, menu: [], lines: [], menuSequence: 0 };
    const api = `${base}/api/receivables`;
    const page = { afterMutation: async () => {} };
    let suggestionTimer;

    async function json(url, options) {
      const request = options?.method && options.method !== 'GET' ? window.csrfFetch : fetch;
      const response = await request(url, { credentials: 'include', ...options });
      const data = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null;
      if (response.status === 401) location.href = '/login';
      if (!response.ok || !data?.success) {
        const error = new Error(data?.error || 'Could not load Receivables.');
        error.status = response.status;
        throw error;
      }
      return data;
    }

    function readUrl() {
      const params = new URLSearchParams(location.search);
      state.date = params.get('all') === '1' ? null : (validDate(params.get('date')) ? params.get('date') : today());
      state.search = (params.get('search') || '').slice(0, 100);
      state.status = ['paid', 'unpaid'].includes(params.get('status')) ? params.get('status') : '';
      $('debt-date').value = state.date || '';
      $('debt-search').value = state.search;
      $('debt-status').value = state.status;
    }

    function writeUrl(replace = false) {
      const url = new URL(location.href);
      for (const key of ['date', 'all', 'search', 'status']) url.searchParams.delete(key);
      url.searchParams.set(state.date ? 'date' : 'all', state.date || '1');
      if (state.search) url.searchParams.set('search', state.search);
      if (state.status) url.searchParams.set('status', state.status);
      history[replace ? 'replaceState' : 'pushState'](null, '', url);
    }

    page.reload = async () => {
      const sequence = ++state.sequence;
      const filters = new URLSearchParams({ page: String(state.recordPage), per_page: '20' });
      const tabFilters = new URLSearchParams({ page: String(state.tabPage), per_page: '20' });
      if (state.date) { filters.set('date', state.date); tabFilters.set('date', state.date); }
      if (state.search) { filters.set('search', state.search); tabFilters.set('search', state.search); }
      if (state.status) filters.set('status', state.status);
      $('receivables-table-body').innerHTML = '<tr><td colspan="12">Loading debts…</td></tr>';
      $('customer-tabs-body').innerHTML = '<tr><td colspan="7">Loading tabs…</td></tr>';
      try {
        const [debts, tabs] = await Promise.all([json(`${api}?${filters}`), json(`${api}/tabs?${tabFilters}`)]);
        if (sequence !== state.sequence) return;
        state.tabs = tabs.data;
        state.records = debts.data;
        render(debts, tabs);
      } catch (error) {
        if (sequence !== state.sequence) return;
        $('receivables-table-body').innerHTML = `<tr><td colspan="12" class="text-danger">${escape(error.message)}</td></tr>`;
        $('customer-tabs-body').innerHTML = '<tr><td colspan="7" class="text-danger">Could not load customer tabs.</td></tr>';
      }
    };

    function render(debts, tabs) {
      $('total-receivables').textContent = Number(debts.totals.all_outstanding).toFixed(2);
      $('selected-taken').textContent = Number(debts.totals.selected_taken).toFixed(2);
      $('selected-owed').textContent = Number(debts.totals.selected_outstanding).toFixed(2);
      $('selected-taken-label').textContent = state.date ? 'Selected date: debt taken' : 'All dates: debt taken';
      $('selected-owed-label').textContent = state.date ? 'Selected date: still owed' : 'All dates: still owed';
      $('records-date-label').textContent = state.date || '(Show All Utang)';
      $('tabs-date-heading').textContent = state.date ? 'Debt taken on selected date' : 'All dates: tab orders';
      $('receivables-count').textContent = `${debts.pagination.total} debt record(s) found`;
      $('open-tabs-count').textContent = `${tabs.pagination.total} open tab(s) found`;
      $('debt-all').classList.toggle('active', !state.date);
      $('debt-today').classList.toggle('active', state.date === today());
      $('receivables-table-body').innerHTML = debts.data.length ? debts.data.map(row => `<tr>
        <td>${escape(row.customer_name)}</td><td>${escape(row.customer_contact) || '—'}</td>
        <td>${escape(row.items)}</td><td>${escape(row.notes) || '—'} <button type="button" class="btn btn-link btn-sm p-0" data-notes="${row.id}">Edit</button></td>
        <td>${pesos(row.amount_owed)}</td><td>${pesos(row.partial_paid)}</td><td>${pesos(row.amount_owed - row.partial_paid)}</td>
        <td>${escape(row.incurred_date)}</td><td>${escape(row.due_date)}</td>
        <td>${row.paid ? '<span class="badge bg-success">Paid</span>' : '<span class="badge bg-warning text-dark">Unpaid</span>'}</td>
        <td>${escape(row.created_by)}</td><td>${row.tab_id ? `<button type="button" class="btn btn-sm btn-outline-secondary" data-view-tab="${row.tab_id}">View cycle</button>` : '—'}</td></tr>`).join('') : '<tr><td colspan="12" class="text-muted">No debt records match this date and search.</td></tr>';
      $('customer-tabs-body').innerHTML = tabs.data.length ? tabs.data.map(tab => `<tr>
        <td>${escape(tab.customer_name)}</td><td>${escape(tab.customer_contact) || '—'}</td>
        <td>${pesos(tab.date_taken_amount)}</td><td>${pesos(tab.orders_total)}</td><td>${pesos(tab.paid_total)}</td>
        <td class="fw-semibold">${pesos(tab.outstanding_balance)}</td><td class="text-nowrap">
        <button type="button" class="btn btn-sm btn-outline-warning" data-add-tab="${tab.id}">Add order</button>
        <button type="button" class="btn btn-sm btn-warning" data-view-tab="${tab.id}">View tab</button></td></tr>`).join('') : '<tr><td colspan="7" class="text-muted">No open customer tabs match this date and search.</td></tr>';
      for (const [prefix, pagination] of [['records', debts.pagination], ['tabs', tabs.pagination]]) {
        $(`${prefix}-page`).textContent = `Page ${pagination.page} of ${pagination.pages || 1}`;
        $(`${prefix}-prev`).disabled = !pagination.has_prev;
        $(`${prefix}-next`).disabled = !pagination.has_next;
      }
    }

    function resetSuggestions(message = 'Type at least two letters of a name or contact.') {
      state.suggestions = [];
      $('matchingTabs').replaceChildren(new Option('New customer / keep typing', ''));
      $('matchingTabs').size = 1;
      $('matchingCustomersStatus').textContent = message;
    }

    async function suggestions(source = 'name') {
      const sequence = ++state.suggestionSequence;
      const name = normName($('customerName').value);
      const contact = normContact($('customerContact').value);
      const select = $('matchingTabs');
      const query = source === 'contact' && contact.length >= 2 ? $('customerContact').value :
        name.length >= 2 ? $('customerName').value : contact.length >= 2 ? $('customerContact').value : '';
      resetSuggestions();
      if (!query) return;
      $('matchingCustomersStatus').textContent = 'Searching all customer dates…';
      try {
        const result = await json(`${api}/customer-suggestions?${new URLSearchParams({ q: query })}`);
        if (sequence !== state.suggestionSequence) return;
        state.suggestions = result.data;
        result.data.forEach((customer, index) => select.add(new Option(
          `${customer.customer_name} · ${customer.customer_contact || 'no contact'} · ${customer.label}`, String(index))));
        select.size = Math.min(result.data.length + 1, 5);
        $('matchingCustomersStatus').textContent = result.data.length ?
          'Choose a customer, or keep typing to enter a new one. Matching contacted open tabs are reused on save.' :
          'No matching customer found. Enter a new customer.';
      } catch (error) {
        if (sequence !== state.suggestionSequence) return;
        resetSuggestions('Customer lookup failed. Retry typing before choosing an existing customer.');
        showToast(error.message, 'error');
      }
    }

    function newReceivable(tab = null) {
      ++state.suggestionSequence;
      clearTimeout(suggestionTimer);
      $('receivable-form').reset();
      state.selectedCustomer = null;
      state.lines = [];
      entryMode();
      loadMenu();
      $('customerName').readOnly = !!tab;
      $('customerContact').readOnly = !!tab;
      resetSuggestions();
      if (tab) {
        $('customerName').value = tab.customer_name;
        $('customerContact').value = tab.customer_contact;
        const customer = { customer_name: tab.customer_name, customer_contact: tab.customer_contact,
          open_tab_id: tab.id, account_id: tab.account_id, label: `Open tab #${tab.id}` };
        state.suggestions = [customer];
        state.selectedCustomer = customer;
        $('matchingTabs').add(new Option(`${tab.customer_name} · ${customer.label}`, '0'));
        $('matchingTabs').value = '0';
        $('matchingCustomersStatus').textContent = `Adding to open tab #${tab.id}.`;
      }
      $('incurredDate').value = today();
      $('dueDate').value = today();
      $('addReceivableModalLabel').textContent = tab ? `Add order for ${tab.customer_name}` : 'Add Receivable';
      bootstrap.Modal.getOrCreateInstance($('addReceivableModal')).show();
    }

    async function openTab(tabId) {
      try {
        const [detailResult, paymentResult] = await Promise.all([
          json(`${api}/tabs/${tabId}`), json(`${api}/tabs/${tabId}/payments`)
        ]);
        const tab = detailResult.data;
        state.detail = tab;
        $('viewCustomerName').textContent = tab.customer_name;
        $('tab-contact').textContent = `Contact: ${tab.customer_contact || 'none'} · Tab #${tab.id}`;
        if ($('tab-export-statement')) $('tab-export-statement').href = `/admin/reports?tab_id=${tab.id}`;
        $('viewOrdersTotal').textContent = pesos(tab.orders_total);
        $('viewPaidTotal').textContent = pesos(tab.paid_total);
        $('viewOutstandingBalance').textContent = pesos(tab.outstanding_balance);
        $('customerPaymentControls').classList.toggle('d-none', !tab.open || tab.outstanding_balance <= 0);
        $('customerPaymentAmount').value = '';
        $('view-order-table-body').innerHTML = tab.records.map(row => `<tr><td>${escape(row.incurred_date)}</td>
          <td>${escape(row.items)}</td><td>${escape(row.notes) || '—'} <button type="button" class="btn btn-link btn-sm p-0" data-notes="${row.id}">Edit</button></td>
          <td>${pesos(row.amount_owed)}</td><td>${pesos(row.partial_paid)}</td><td>${pesos(row.amount_owed - row.partial_paid)}</td><td>${escape(row.due_date)}</td><td>${escape(row.created_by)}</td></tr>`).join('');
        $('customerPaymentHistory').innerHTML = paymentResult.data.length ? paymentResult.data.map(payment => `<tr>
          <td>${escape(new Date(payment.received_at).toLocaleString('en-PH', { timeZone: 'Asia/Manila' }))}</td>
          <td>${pesos(payment.amount)}<br><small>${payment.allocations.map(a => `#${a.receivable_id} ${escape(a.item)}: ${a.balance_before == null ? 'historical balance unavailable' : `${pesos(a.balance_before)} → ${pesos(a.balance_after)}`}`).join('<br>')}</small></td>
          <td>${escape(payment.payment_method)}</td><td>${escape(payment.received_by)}</td></tr>`).join('') : '<tr><td colspan="4">No payments recorded yet.</td></tr>';
        bootstrap.Modal.getOrCreateInstance($('viewOrderModal')).show();
      } catch (error) { showToast(error.message, 'error'); }
    }

    async function editNotes(recId, reopen = false) {
      const row = state.detail?.records.find(item => item.id === recId) || state.records.find(item => item.id === recId);
      const notes = prompt('Borrowed utensils / notes', row?.notes || '');
      if (notes === null) return;
      try {
        await json(`${api}/${recId}/notes`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ notes }) });
        await page.afterMutation();
        if (reopen && state.detail) await openTab(state.detail.id);
      } catch (error) { showToast(error.message, 'error'); }
    }

    function menuOptions() {
      const term = $('receivableMenuSearch').value.trim().toLocaleLowerCase();
      const select = $('receivableMenuItem');
      select.replaceChildren(new Option('Choose a menu item', ''));
      for (const item of state.menu.filter(item => item.name.toLocaleLowerCase().includes(term))) {
        select.add(new Option(`${item.name} · ${pesos(item.price)}`, item.id));
      }
      mealOptions();
    }

    function mealOptions() {
      const item = state.menu.find(row => row.id === Number($('receivableMenuItem').value));
      for (const [id, key] of [['receivableNoRice', 'can_remove_rice'], ['receivableNoEgg', 'can_remove_egg']]) {
        $(id).disabled = !item?.[key];
        $(id).checked = false;
      }
    }

    async function loadMenu() {
      const sequence = ++state.menuSequence;
      $('receivableMenuStatus').textContent = 'Loading menu…';
      $('receivableAddItem').disabled = true;
      try {
        const result = await json(`${api}/menu`);
        if (sequence !== state.menuSequence) return;
        state.menu = result.data;
        menuOptions();
        let invalidLine = false;
        for (const line of state.lines) {
          const item = state.menu.find(item => item.id === line.menu_item_id);
          if (!item || (line.no_rice && !item.can_remove_rice) || (line.no_egg && !item.can_remove_egg)) {
            invalidLine = true; continue;
          }
          line.name = item.name;
          line.expected_base_price = item.price;
          line.unitCents = Math.round(Number(item.price) * 100) - 1800 * (Number(line.no_rice) + Number(line.no_egg));
          if (line.unitCents <= 0) invalidLine = true;
        }
        renderLines();
        $('receivableMenuStatus').textContent = invalidLine ? 'Some selected items/options are unavailable. Remove them before saving.' :
          state.lines.length ? 'Menu refreshed. Review the item prices and total before saving.' :
          result.data.length ? '' : 'No menu items found. Retry or use a verified manual entry.';
        $('receivableAddItem').disabled = !result.data.length;
      } catch (error) {
        if (sequence !== state.menuSequence) return;
        state.menu = [];
        menuOptions();
        $('receivableMenuStatus').textContent = error.message + ' Use Refresh menu to retry.';
      }
    }

    function entryMode() {
      const menu = $('receivableEntryMode').value === 'menu';
      $('receivableMenuPanel').hidden = !menu;
      $('itemsDesc').readOnly = $('amountOwed').readOnly = menu;
      if (menu) renderLines();
      else { $('itemsDesc').value = ''; $('amountOwed').value = ''; }
    }

    function renderLines() {
      const total = state.lines.reduce((sum, item) => sum + item.unitCents * item.quantity, 0);
      $('receivableItemLines').innerHTML = state.lines.map((item, index) => `<li class="border-top py-2">
        ${item.quantity} × ${escape(item.name)}${item.no_rice ? ' (no rice)' : ''}${item.no_egg ? ' (no egg)' : ''}<br>
        <small>${pesos(item.unitCents / 100)} each · ${pesos(item.unitCents * item.quantity / 100)}</small>
        <button type="button" class="btn btn-sm btn-outline-danger ms-1" data-remove-credit-line="${index}">Remove</button></li>`).join('');
      if ($('receivableEntryMode').value === 'menu') {
        $('itemsDesc').value = state.lines.map(item => `${item.quantity} × ${item.name}${item.no_rice ? ' (no rice)' : ''}${item.no_egg ? ' (no egg)' : ''}`).join('; ');
        $('amountOwed').value = total ? (total / 100).toFixed(2) : '';
      }
    }

    document.addEventListener('DOMContentLoaded', () => {
      readUrl();
      writeUrl(true);
      page.reload();
      const change = () => { state.recordPage = state.tabPage = 1; writeUrl(); page.reload(); };
      $('debt-date').addEventListener('change', () => { state.date = $('debt-date').value || null; change(); });
      $('debt-today').addEventListener('click', () => { state.date = $('debt-date').value = today(); change(); });
      $('debt-all').addEventListener('click', () => { state.date = null; $('debt-date').value = ''; change(); });
      $('debt-status').addEventListener('change', () => { state.status = $('debt-status').value; change(); });
      let debounce;
      $('debt-search').addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(() => { state.search = $('debt-search').value.trim(); change(); }, 250); });
      $('debt-clear').addEventListener('click', () => { $('debt-search').value = state.search = ''; clearTimeout(debounce); change(); });
      for (const prefix of ['records', 'tabs']) for (const direction of ['prev', 'next']) {
        $(`${prefix}-${direction}`).addEventListener('click', () => { state[prefix === 'records' ? 'recordPage' : 'tabPage'] += direction === 'next' ? 1 : -1; page.reload(); });
      }
      addEventListener('popstate', () => { readUrl(); state.recordPage = state.tabPage = 1; page.reload(); });
      $('new-receivable').addEventListener('click', () => newReceivable());
      $('receivableEntryMode').addEventListener('change', entryMode);
      $('receivableRefreshMenu').addEventListener('click', loadMenu);
      $('receivableMenuSearch').addEventListener('input', menuOptions);
      $('receivableMenuItem').addEventListener('change', mealOptions);
      $('receivableItemLines').addEventListener('click', event => {
        const button = event.target.closest('[data-remove-credit-line]');
        if (button) { state.lines.splice(Number(button.dataset.removeCreditLine), 1); renderLines(); }
      });
      $('receivableAddItem').addEventListener('click', () => {
        const item = state.menu.find(row => row.id === Number($('receivableMenuItem').value));
        const quantity = Number($('receivableMenuQty').value);
        if (!item || !Number.isInteger(quantity) || quantity < 1 || quantity > 999999 || state.lines.length >= 100) {
          $('receivableMenuStatus').textContent = 'Choose an item and a whole quantity. Up to 100 lines are allowed.'; return;
        }
        const no_rice = $('receivableNoRice').checked, no_egg = $('receivableNoEgg').checked;
        const unitCents = Math.round(Number(item.price) * 100) - 1800 * (Number(no_rice) + Number(no_egg));
        if (unitCents <= 0) { $('receivableMenuStatus').textContent = 'Check this menu price and meal options.'; return; }
        state.lines.push({ menu_item_id: item.id, quantity, no_rice, no_egg, expected_base_price: item.price, name: item.name, unitCents });
        $('receivableMenuStatus').textContent = '';
        renderLines();
      });
      for (const [id, source] of [['customerName', 'name'], ['customerContact', 'contact']]) {
        $(id).addEventListener('input', () => {
          state.selectedCustomer = null;
          ++state.suggestionSequence;
          clearTimeout(suggestionTimer);
          suggestionTimer = setTimeout(() => suggestions(source), 250);
        });
      }
      $('matchingTabs').addEventListener('change', () => {
        const selected = $('matchingTabs').value;
        state.selectedCustomer = selected === '' ? null : state.suggestions[Number(selected)];
        $('customerName').readOnly = $('customerContact').readOnly = !!state.selectedCustomer;
        if (state.selectedCustomer) {
          $('customerName').value = state.selectedCustomer.customer_name;
          $('customerContact').value = state.selectedCustomer.customer_contact;
          $('matchingCustomersStatus').textContent = state.selectedCustomer.label;
        } else {
          $('matchingCustomersStatus').textContent = 'Enter a new customer, or choose a match.';
        }
      });
      $('customer-tabs-body').addEventListener('click', event => {
        const view = event.target.closest('[data-view-tab]');
        const add = event.target.closest('[data-add-tab]');
        if (view) openTab(Number(view.dataset.viewTab));
        if (add) newReceivable(state.tabs.find(tab => tab.id === Number(add.dataset.addTab)));
      });
      for (const id of ['receivables-table-body', 'view-order-table-body']) $(id).addEventListener('click', event => {
        const button = event.target.closest('[data-notes]');
        if (button) editNotes(Number(button.dataset.notes), id === 'view-order-table-body');
        const view = event.target.closest('[data-view-tab]');
        if (view) openTab(Number(view.dataset.viewTab));
      });
      $('receivable-form').addEventListener('submit', async event => {
        event.preventDefault();
        const button = $('save-receivable');
        if (button.disabled) return;
        button.disabled = true;
        try {
          const payload = Object.fromEntries(new FormData(event.currentTarget));
          if (state.selectedCustomer?.open_tab_id) payload.tab_id = state.selectedCustomer.open_tab_id;
          if (state.selectedCustomer?.account_id) payload.account_id = state.selectedCustomer.account_id;
          if ($('receivableEntryMode').value === 'menu') {
            if (!state.lines.length) throw new Error('Add at least one menu item.');
            payload.items = state.lines.map(({ menu_item_id, quantity, no_rice, no_egg, expected_base_price }) =>
              ({ menu_item_id, quantity, no_rice, no_egg, expected_base_price }));
          }
          const result = await json(api, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
          bootstrap.Modal.getInstance($('addReceivableModal'))?.hide();
          await page.afterMutation();
          showToast(`Debt recorded on tab #${result.data.tab_id}.`, 'success');
        } catch (error) {
          if (error.status === 409) {
            state.selectedCustomer = null;
            $('customerName').readOnly = $('customerContact').readOnly = false;
            await suggestions('name');
          }
          showToast(error.message, 'error');
        }
        finally { button.disabled = false; }
      });
      $('payment-full').addEventListener('click', () => { $('customerPaymentAmount').value = state.detail?.outstanding_balance.toFixed(2) || ''; });
      $('recordCustomerPaymentBtn').addEventListener('click', async () => {
        const amount = $('customerPaymentAmount').value.trim();
        if (!/^\d+(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0 || Number(amount) > state.detail.outstanding_balance) {
          showToast('Enter an amount up to the whole-tab balance.', 'error'); return;
        }
        const button = $('recordCustomerPaymentBtn');
        if (button.disabled) return;
        button.disabled = true;
        let saved = false;
        try {
          const tabId = state.detail.id;
          await json(`${api}/tabs/${tabId}/payments`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount, payment_method: $('customerPaymentMethod').value }) });
          saved = true;
          await page.afterMutation();
          await openTab(tabId);
          showToast('Payment recorded.', 'success');
        } catch (error) { showToast(saved ? 'Payment saved. Reload to review the balance.' : error.message, 'error'); }
        finally { button.disabled = false; }
      });
    });
    return page;
  };
})();

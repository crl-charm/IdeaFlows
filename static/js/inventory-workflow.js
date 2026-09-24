/* Existing inventory cards/tables share one accessible stock-action dialog. */
window.InventoryUI = (() => {
  const root = document.getElementById('inventory-workflow');
  const admin = root.dataset.admin === 'true';
  const kitchen = root.dataset.kitchen === 'true';
  const dialog = document.getElementById('stock-dialog');
  const servingsDialog = document.getElementById('servings-dialog');
  const el = id => document.getElementById(id);
  const items = new Map();
  let meals = [];
  const escape = value => { const node = document.createElement('span'); node.textContent = String(value ?? ''); return node.innerHTML; };
  const labels = {prepared:'Manual servings',direct:'Counted pieces',recipe:'Manual servings',untracked:'Quantity not tracked'};
  let current = null;
  function actions(item) {
    items.set(item.id, item);
    let buttons = '';
    const button = (action, label) => `<button type="button" class="btn-icon" onclick="InventoryUI.open(${Number(item.id)}, '${action}')">${label}</button>`;
    if ((admin && ['prepared','direct'].includes(item.inventory_mode)) || (kitchen && item.inventory_mode === 'prepared')) {
      buttons += button('add', item.inventory_mode === 'prepared' ? '+ Add Batch' : '+ Receive stock');
      buttons += button('waste', 'Record waste');
      buttons += button('sold_out', 'Mark sold out');
      if (admin) buttons += button('count', 'Correct count');
    }
    return buttons ? `<div class="inventory-actions d-flex flex-wrap gap-2">${buttons}</div>` : '';
  }
  function status(item) {
    return `<span class="inventory-state ${escape(item.availability_state)}">${escape(item.availability_message)}</span>`;
  }
  function fields() {
    const setup = current.action === 'setup';
    const counted = ['prepared','direct'].includes(el('stock-mode').value);
    const showQuantity = setup ? counted : current.action !== 'sold_out';
    el('stock-mode-field').hidden = !setup;
    el('stock-threshold-field').hidden = !(setup && counted);
    el('stock-quantity-field').hidden = !showQuantity;
    el('stock-quantity').required = showQuantity;
    el('stock-reason').required = current.action !== 'add';
    el('stock-quantity').min = ['setup','count'].includes(current.action) ? '0' : '1';
    el('stock-quantity-label').textContent = setup || current.action === 'count' ? 'Actual quantity available now' : current.action === 'waste' ? 'How many can no longer be sold?' : current.action === 'add' && current.item.inventory_mode === 'prepared' ? 'How many servings were prepared?' : 'How many are you adding?';
  }
  function open(id, action) {
    const item = items.get(id);
    if (!item) return;
    current = {item, action, key:crypto.randomUUID()};
    el('stock-form').reset();
    el('stock-error').textContent = '';
    el('stock-item-name').textContent = item.name;
    el('stock-dialog-title').textContent = {setup:'Stock setup',add:item.inventory_mode === 'prepared' ? 'Add Batch' : 'Add stock',waste:'Record waste',sold_out:'Mark sold out',count:'Correct stock count'}[action];
    el('stock-help').textContent = action === 'sold_out' ? 'This sets the remaining count to zero. Enter why the remaining stock is no longer available.' : action === 'setup' ? 'Enter the servings you expect to make. Raw ingredients are updated separately.' : 'Your change will be recorded with your name and time.';
    el('stock-mode').value = item.inventory_mode;
    el('stock-quantity').value = ['setup','count'].includes(action) ? item.stock_qty ?? 0 : '';
    el('stock-threshold').value = item.low_stock_threshold ?? 3;
    fields();
    dialog.showModal();
    if (action === 'add' && item.inventory_mode === 'prepared') {
      fetchJSON(`/inventory/api/menu-items/${id}/last-batch`).then(result => {
        if (current?.item.id === id && current.action === 'add' && result.quantity && !el('stock-quantity').value) el('stock-quantity').value = result.quantity;
      }).catch(() => {});
    }
  }
  el('stock-mode').addEventListener('change', fields);
  el('stock-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (current.action === 'sold_out' && !await showConfirmDialog({title:'Mark sold out?',message:'This sets the remaining stock to zero.',confirmText:'Mark sold out',confirmClass:'btn-warning'})) return;
    const button = el('stock-save');
    button.disabled = true;
    el('stock-error').textContent = '';
    try {
      await fetchJSON(`/inventory/api/menu-items/${current.item.id}/action`, {method:'POST',
        headers:{'Content-Type':'application/json','Idempotency-Key':current.key},
        body:JSON.stringify({action:current.action,inventory_mode:el('stock-mode').value,
          quantity:el('stock-quantity').value,threshold:el('stock-threshold').value,reason:el('stock-reason').value})});
      dialog.close();
      showToast('Stock updated.', 'success');
      window.dispatchEvent(new Event('inventory-changed'));
      if (document.querySelector('.stock-history[open]')) history();
    } catch (error) { el('stock-error').textContent = error.message || 'Could not save. Please try again.'; }
    finally { button.disabled = false; }
  });
  function setMeals(rows) {
    meals = rows.filter(item => ['prepared', 'recipe', 'untracked'].includes(item.inventory_mode));
    if (!servingsDialog) return;
    const select = el('servings-meal');
    const selected = select.value;
    select.innerHTML = meals.map(item => `<option value="${Number(item.id)}">${escape(item.name)}</option>`).join('');
    if (meals.some(item => String(item.id) === selected)) select.value = selected;
    el('servings-count').value = meals.find(item => String(item.id) === select.value)?.available_quantity ?? 0;
  }
  function openServings() {
    if (!servingsDialog || !meals.length) return showToast('Add a menu item first.', 'error');
    el('servings-error').textContent = '';
    servingsDialog.showModal();
  }
  el('servings-meal')?.addEventListener('change', event => {
    el('servings-count').value = meals.find(item => String(item.id) === event.target.value)?.available_quantity ?? 0;
  });
  el('servings-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    const id = Number(el('servings-meal').value);
    const button = el('servings-save');
    button.disabled = true;
    el('servings-error').textContent = '';
    try {
      await fetchJSON(`/inventory/api/menu-items/${id}/action`, {method:'POST',
        headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},
        body:JSON.stringify({action:'servings', quantity:el('servings-count').value})});
      servingsDialog.close();
      showToast('Servings updated.', 'success');
      window.dispatchEvent(new Event('inventory-changed'));
    } catch (error) { el('servings-error').textContent = error.message || 'Could not save servings.'; }
    finally { button.disabled = false; }
  });
  async function history() {
    try {
      const result = await fetchJSON('/inventory/api/history');
      el('stock-history-list').innerHTML = result.data.length ? `<table class="table table-sm align-middle"><thead><tr><th>Item / action</th><th>Quantity</th><th>Who / when</th><th>Reason</th></tr></thead><tbody>${result.data.map(row => `<tr><td>${escape(row.item)}<div class="small text-muted">${escape(row.action.replaceAll('_',' '))}</div></td><td>${escape(row.quantity)}</td><td>${escape(row.actor)}<div class="small">${escape(new Date(row.at).toLocaleString())}</div></td><td>${escape(row.reason)}</td></tr>`).join('')}</tbody></table>` : '<p class="text-muted">Your stock changes will appear here.</p>';
    } catch (error) { el('stock-history-list').textContent = error.message || 'Could not load history.'; }
  }
  async function summary() {
    try {
      const result = await fetchJSON('/inventory/api/prepared-summary');
      el('prepared-summary-list').innerHTML = result.data.length ? `<table class="table table-sm align-middle"><thead><tr><th>Meal</th><th>Batches added</th><th>Ordered</th><th>Voided</th><th>Wasted / sold out</th><th>Ready now</th></tr></thead><tbody>${result.data.map(row => `<tr><td>${escape(row.name)}</td><td>${row.prepared}</td><td>${row.ordered}</td><td>${row.voided}</td><td>${row.wasted}</td><td><strong>${row.remaining}</strong></td></tr>`).join('')}</tbody></table>` : '<p class="text-muted">No prepared meals yet.</p>';
    } catch (error) { el('prepared-summary-list').textContent = error.message || 'Could not load summary.'; }
  }
  document.querySelector('.stock-history')?.addEventListener('toggle', event => { if(event.target.open) history(); });
  document.querySelector('.prepared-summary')?.addEventListener('toggle', event => { if(event.target.open) summary(); });
  return {actions,status,open,openServings,setMeals,escape,labels};
})();

"use strict";
(function () {
  const el = id => document.getElementById(id);
  const form = el('missedCheckoutForm');
  if (!form) return;
  let sessionId = null, preview = null, version = 0, customPaymentTime = false;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP'}).format(value);
  function ready() { el('missedSaveButton').disabled = !(preview?.matches && el('missedPaymentConfirmed').checked); }
  function invalidate() {
    version++; preview = null; el('missedPreview').hidden = true;
    el('missedPaymentConfirmed').checked = false;
    el('missedCheckoutError').textContent = ''; ready();
  }
  function payload() {
    return {departure_at:el('missedDeparture').value, paid_at:el('missedPaidAt').value,
      amount_received:el('missedAmount').value, payment_method:el('missedMethod').value,
      collector_id:Number(el('missedCollector').value), reason:el('missedReason').value,
      note:el('missedNote').value, discount_type:el('missedDiscount').value,
      discount_item_id:el('missedDiscount').value ? el('missedDiscountItem').value || null : null,
      amount_tendered:el('missedMethod').value === 'cash' ? el('missedTendered').value || null : null};
  }
  window.openMissedCheckout = async function (id, customer, orders, discountType, discountItem) {
    try {
      const options = await fetchJSON('/api/missed-checkout/options');
      form.reset(); sessionId = id; customPaymentTime = false; invalidate();
      el('missedCustomerName').textContent = customer;
      const max = new Date(Date.parse(options.server_now) + 8 * 3600000).toISOString().slice(0,16);
      el('missedDeparture').max = max; el('missedPaidAt').max = max;
      const collectors = el('missedCollector');
      collectors.replaceChildren(new Option('Choose actual collector',''));
      options.collectors.forEach(row => collectors.add(new Option(row.name + (row.active ? '' : ' (inactive)'),row.id)));
      const items = el('missedDiscountItem');
      items.replaceChildren(new Option('Choose item if discounted',''));
      orders.forEach(row=>items.add(new Option(row.item_name + ' — one × ' + money(row.price),row.id)));
      el('missedItemGroup').hidden = !orders.length;
      el('missedDiscount').value = discountType || '';
      el('missedDiscountItem').value = discountItem || '';
      el('missedNote').required = false;
      const summary = el('receiptModal');
      summary.addEventListener('hidden.bs.modal',()=>bootstrap.Modal.getOrCreateInstance(el('missedCheckoutModal')).show(),{once:true});
      bootstrap.Modal.getOrCreateInstance(summary).hide();
    } catch (error) { showToast(error.message || 'Could not open missed checkout.','error'); }
  };
  function changed(event) {
    if (event.target.id === 'missedPaymentConfirmed') { ready(); return; }
    if (event.target.id === 'missedPaidAt') customPaymentTime = true;
    if (event.target.id === 'missedDeparture' && !customPaymentTime) el('missedPaidAt').value = el('missedDeparture').value;
    if (event.target.id === 'missedReason') el('missedNote').required = el('missedReason').value === 'other';
    invalidate();
  }
  form.addEventListener('input', changed);
  form.addEventListener('change', changed);
  el('missedPreviewButton').addEventListener('click', async () => {
    if (!form.reportValidity()) return;
    const revision = version;
    try {
      const data = await runButtonAction(el('missedPreviewButton'),{label:'Reviewing...'},()=>fetchJSON(
        `/api/sessions/${sessionId}/missed-checkout/preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())}));
      if (revision !== version) return;
      preview = data;
      el('missedPreview').innerHTML = `<div class="row g-3"><div class="col-12 col-sm-6"><strong>Current running estimate</strong><div>${money(data.before.total)}</div></div><div class="col-12 col-sm-6"><strong>Corrected bill</strong><div>${money(data.total)}</div></div></div>
        <dl class="row small mt-3 mb-0"><dt class="col-6">Billable time</dt><dd class="col-6">${escape(Math.floor(data.billable_seconds / 3600))}h ${escape(Math.floor(data.billable_seconds % 3600 / 60))}m</dd><dt class="col-6">Time bill</dt><dd class="col-6">${money(data.time_bill)}</dd><dt class="col-6">Food bill</dt><dd class="col-6">${money(data.food_bill)}</dd><dt class="col-6">Discount</dt><dd class="col-6">${money(data.discount)}</dd><dt class="col-6">Reported payment</dt><dd class="col-6">${money(data.amount_received)}</dd><dt class="col-6">Difference</dt><dd class="col-6">${money(data.difference)}</dd></dl>
        <p class="small mb-0">Departure ${escape(data.departure_at.replace('T',' '))} · Paid ${escape(data.paid_at.replace('T',' '))} · Received by ${escape(data.collector)}. All times Manila.</p>
        ${data.matches ? '' : '<p class="text-danger small mt-2 mb-0">Review the arrival/departure, orders, discount, and amount received before continuing.</p>'}
        ${data.possible_existing_payments.map(item=>`<p class="text-warning small mt-2 mb-0">${escape(item)}</p>`).join('')}`;
      el('missedPreview').hidden = false; ready();
    } catch (error) { preview = null; ready(); el('missedCheckoutError').textContent = error.message || 'Could not review the bill.'; }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!preview?.matches || !el('missedPaymentConfirmed').checked || !form.reportValidity()) return;
    const data = {...payload(), preview_token:preview.preview_token, payment_confirmed:true};
    el('missedCheckoutFields').disabled = true;
    try {
      const result = await runButtonAction(el('missedSaveButton'),{label:'Recording...'},key=>fetchJSON(
        `/api/sessions/${sessionId}/missed-checkout`,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(data)}));
      window.location.assign(result.receipt_url);
    } catch (error) {
      preview = null; el('missedPaymentConfirmed').checked = false; ready();
      el('missedCheckoutError').textContent = error.message || 'Could not save. Refresh and review before retrying.';
    } finally { el('missedCheckoutFields').disabled = false; }
  });
})();

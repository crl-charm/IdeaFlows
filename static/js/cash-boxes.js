(function () {
  const $ = id => document.getElementById(id);
  if (!$('cashBoxesModal')) return;
  const currency = new Intl.NumberFormat('en-PH', {style:'currency', currency:'PHP'});
  const dateTime = new Intl.DateTimeFormat('en-PH', {timeZone:'Asia/Manila', dateStyle:'medium', timeStyle:'short'});
  const dateOnly = new Intl.DateTimeFormat('en-PH', {timeZone:'Asia/Manila', dateStyle:'medium'});
  const money = value => value == null ? '—' : currency.format(value);
  const text = value => window.escapeHTML(String(value ?? '—'));
  const cashDate = value => dateOnly.format(new Date(value + 'T12:00:00+08:00'));
  let today = new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Manila', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
  let currentStatus = null, isSaving = false, historyInitialized = false;
  let statusRequest = 0, historyRequest = 0;
  let pendingAction = null, returnFocus = null, topupAttempt = null, modalTrigger = null;
  let entries = new Map();

  function error(message) {
    $('cashBoxesError').textContent = message;
    $('cashBoxesError').classList.toggle('d-none', !message);
  }
  function success(message) {
    $('cashBoxesSuccess').textContent = message;
    $('cashBoxesSuccess').classList.toggle('d-none', !message);
  }
  async function cashJSON(url, options) {
    const data = await fetchJSON(url, options);
    if (!data.success) throw new Error(data.error || 'Cash records are unavailable.');
    return data;
  }
  function updateForms() {
    $('cashTopupFields').disabled = isSaving || !currentStatus;
    $('cashWithdrawalFields').disabled = isSaving || !currentStatus?.opening_date;
    $('cashOtherActions').hidden = !currentStatus?.opening_date;
    $('cashWithdrawalSubmit').disabled = $('cashOwnerDebt').value === 'yes';
    $('cashConfirmSubmit').disabled = isSaving;
    $('cashConfirmCancel').disabled = isSaving;
    document.querySelectorAll('#cashHistoryFilter input, #cashHistoryFilter button, #cashHistoryToday, #cashHistoryAll, #cashReload').forEach(el => { el.disabled = isSaving; });
    document.querySelectorAll('#cashHistoryBody [data-correct]').forEach(el => { el.disabled = isSaving || !currentStatus; });
  }
  function dateNotice() {
    $('cashDateNotice').textContent = $('cashDate').value === today ? `Today · ${cashDate(today)}` : `Cash date: ${$('cashDate').value || 'Choose a date'}`;
  }
  function withdrawalBalance() {
    const box = $('cashBoxChoice').value;
    const amount = currentStatus?.balances?.closing[box];
    $('cashWithdrawalBalance').textContent = box && amount != null ? `Available now: ${money(amount)}` : 'Choose a box to see its available cash.';
    $('cashOwnerDebtAdvice').hidden = $('cashOwnerDebt').value !== 'yes';
    updateForms();
  }
  function historyButtons() {
    const start = $('cashHistoryStart').value, end = $('cashHistoryEnd').value;
    $('cashHistoryToday').setAttribute('aria-pressed', String(start === today && end === today));
    $('cashHistoryAll').setAttribute('aria-pressed', String(!start && !end));
  }
  function selectHistoryDate(day) {
    $('cashHistoryStart').value = day;
    $('cashHistoryEnd').value = day;
    historyInitialized = true;
    historyButtons();
  }
  async function loadStatus() {
    const request = ++statusRequest;
    const data = await cashJSON('/api/cash-boxes');
    if (request !== statusRequest) return;
    if (!data.today || (data.opening_date && !Number.isFinite(data.balances?.closing?.petty))) throw new Error('The cash balance could not be read.');
    currentStatus = data;
    today = data.today;
    if (!$('cashDate').value) $('cashDate').value = today;
    if (!$('cashWithdrawalDate').value) $('cashWithdrawalDate').value = today;
    for (const id of ['cashDate','cashWithdrawalDate']) {
      $(id).max = today;
      $(id).min = data.opening_date || '';
    }
    if (!historyInitialized) selectHistoryDate(today);
    $('cashPettyBalance').textContent = data.balances ? money(data.balances.closing.petty) : 'Not started';
    $('cashPettyBalance').classList.toggle('text-danger', !!data.balances && data.balances.closing.petty < 0);
    $('cashBalanceStatus').textContent = data.balances?.closing.petty < 0
      ? 'The tracked balance is negative. Review the recorded entries and spending.'
      : data.balances ? 'Cash remaining from recorded petty cash entries and spending. Unused cash carries forward.' : 'Add petty cash to start tracking.';
    if (data.balances?.unassigned_cash_entries) $('cashBalanceStatus').textContent += ' Some older cash payments have no known box; review their source histories.';
    dateNotice();
    withdrawalBalance();
  }
  const field = (label, value) => `<div><dt>${text(label)}</dt><dd>${value}</dd></div>`;
  function renderHistory(rows) {
    closeConfirmation(false);
    const opened = new Set([...$('cashHistoryBody').querySelectorAll('details[open]')].map(el => el.dataset.entry));
    entries = new Map(rows.map(entry => [String(entry.id), entry]));
    const reversals = new Map(rows.filter(entry => entry.reverses_id).map(entry => [entry.reverses_id,entry.id]));
    const replacements = new Map(rows.filter(entry => entry.replaces_id).map(entry => [entry.replaces_id,entry.id]));
    const names = {owner_topup:'Petty cash added', withdrawal:'Cash taken out', reversal:'Entry correction', opening:'Tracking started'};
    $('cashHistoryBody').innerHTML = rows.map(entry => {
      const corrected = reversals.has(entry.id);
      const label = entry.replaces_id ? 'Corrected opening count' : names[entry.kind] || entry.kind;
      const box = entry.box === 'petty' ? 'Petty cash' : 'Customer cash';
      const links = [['Corrects entry',entry.reverses_id],['Replaces entry',entry.replaces_id],['Correction entry',reversals.get(entry.id)],['Replacement entry',replacements.get(entry.id)]]
        .filter(([,id]) => id).map(([name,id]) => field(name,`<a href="#cash-entry-${id}">#${id}</a>`)).join('');
      return `<details class="cash-entry" id="cash-entry-${entry.id}" data-entry="${entry.id}" ${opened.has(String(entry.id)) ? 'open' : ''}>
        <summary><span class="cash-entry-heading">${entry.effect > 0 ? '+' : ''}${money(entry.effect)} · ${text(label)}</span>${corrected ? ' <span class="badge text-bg-secondary">Corrected</span>' : ''}<span class="cash-entry-meta">${text(cashDate(entry.effective_date))} · ${text(box)}<br>Recorded by ${text(entry.actor)}</span></summary>
        <div class="cash-entry-body"><dl class="cash-entry-fields">${field('Entry',`#${entry.id}`)}${field('Recorded at (Manila)',text(dateTime.format(new Date(entry.recorded_at))))}${field('Cash box',text(box))}${field('Payment method',text(entry.payment_method))}${field('Cash date',text(entry.effective_date))}${links}${entry.kind === 'owner_topup' ? field('Owner repayment needed',entry.repay_owner ? 'Yes — recorded in Payables' : 'No') : ''}</dl>
        <p class="small text-muted mb-1">Balances when this entry was recorded:</p><dl class="cash-entry-fields">${field('Before',money(entry.balance_before))}${field('After',money(entry.balance_after))}</dl>
        ${entry.recipient ? `<p class="cash-entry-note"><strong>Received by:</strong> ${text(entry.recipient)}</p>` : ''}${entry.note ? `<p class="cash-entry-note"><strong>${entry.kind === 'reversal' ? 'Correction reason' : 'Note'}:</strong> ${text(entry.note)}</p>` : ''}
        ${entry.kind !== 'reversal' && !corrected ? `<button type="button" class="btn btn-sm btn-outline-danger" data-correct="${entry.id}">Correct entry</button>` : ''}</div></details>`;
    }).join('');
    updateForms();
  }
  async function loadHistory() {
    const start = $('cashHistoryStart').value, end = $('cashHistoryEnd').value;
    if (start && end && start > end) throw new Error('History From date must be on or before Through date.');
    const request = ++historyRequest;
    const params = new URLSearchParams();
    if (start) params.set('start_date',start);
    if (end) params.set('end_date',end);
    $('cashHistoryStatus').textContent = 'Loading history...';
    const data = await cashJSON(`/api/cash-boxes/history?${params}`);
    if (request !== historyRequest) return;
    if (!Array.isArray(data.data)) throw new Error('The cash history could not be read.');
    renderHistory(data.data);
    $('cashHistoryStatus').textContent = data.data.length ? `${data.data.length} recorded entries · ${start || 'Start'} to ${end || 'latest'}` : 'No cash entries for these dates.';
    historyButtons();
  }
  async function refresh() {
    let fresh = true;
    $('cashReload').classList.add('d-none');
    try { await loadStatus(); }
    catch (ex) {
      fresh = false;
      currentStatus = null;
      $('cashPettyBalance').textContent = '—';
      $('cashBalanceStatus').textContent = 'Cash balance unavailable. Refresh to try again.';
      error(ex.message || 'Could not load the cash balance.');
      updateForms();
    }
    try { await loadHistory(); }
    catch (ex) { fresh = false; $('cashHistoryStatus').textContent = `Could not refresh history. ${ex.message || 'Please try again.'} Previously loaded entries may be out of date.`; }
    $('cashReload').classList.toggle('d-none', fresh);
    return fresh;
  }
  async function historyOnly() {
    if (isSaving) return;
    error('');
    try { await loadHistory(); }
    catch (ex) { $('cashHistoryStatus').textContent = ex.message || 'Could not load history.'; $('cashReload').classList.remove('d-none'); }
  }
  async function postCash(button, url, payload, label) {
    const fingerprint = JSON.stringify({url,payload});
    if (button.dataset.actionFingerprint !== fingerprint) {
      delete button.dataset.retryRequestKey;
      button.dataset.actionFingerprint = fingerprint;
    }
    return runButtonAction(button,{label},key => cashJSON(url,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(payload)}));
  }
  async function saved(day, message) {
    selectHistoryDate(day);
    window.dispatchEvent(new Event('cash-boxes-updated'));
    const fresh = await refresh();
    success(`${message}${fresh && currentStatus?.balances ? ` Petty cash available: ${money(currentStatus.balances.closing.petty)}.` : ''}`);
    if (!fresh) error('The entry was saved, but its balance or history could not refresh. Use Refresh cash boxes to check the latest records.');
  }
  function writeError(ex) {
    error(!ex.status || ex.status >= 500 ? 'The save could not be confirmed. Keep these details and retry; the system will check for an existing entry.' : ex.message);
    $('cashBoxesError').focus();
  }
  function closeConfirmation(focus = true) {
    $('cashBoxesConfirmForm').classList.add('d-none');
    $('cashConfirmationHome').append($('cashBoxesConfirmForm'));
    $('cashCorrectionReason').value = '';
    $('cashReplacementAmount').value = '';
    pendingAction = null;
    if (focus && returnFocus?.isConnected) returnFocus.focus({preventScroll:true});
    returnFocus = null;
  }
  function confirmAction(action, source, host, title, message) {
    if (isSaving) return;
    closeConfirmation(false);
    pendingAction = action;
    returnFocus = source;
    const correcting = action.type === 'correction', opening = correcting && action.kind === 'opening';
    $('cashConfirmTitle').textContent = title;
    $('cashConfirmMessage').textContent = message;
    $('cashCorrectionReasonGroup').classList.toggle('d-none',!correcting);
    $('cashCorrectionReason').disabled = !correcting;
    $('cashReplacementGroup').classList.toggle('d-none',!opening);
    $('cashReplacementAmount').disabled = !opening;
    $('cashConfirmSubmit').textContent = correcting ? 'Correct entry' : 'Record withdrawal';
    host.append($('cashBoxesConfirmForm'));
    $('cashBoxesConfirmForm').classList.remove('d-none');
    $('cashBoxesConfirmForm').scrollIntoView({block:'nearest'});
    (correcting ? $('cashCorrectionReason') : $('cashConfirmSubmit')).focus();
  }
  window.openCashBoxes = async function () {
    if (!$('cashBoxesModal').classList.contains('show')) modalTrigger = document.activeElement;
    bootstrap.Modal.getOrCreateInstance($('cashBoxesModal')).show();
    if (isSaving) return;
    error(''); success(''); closeConfirmation(false);
    currentStatus = null;
    historyInitialized = false;
    if (!$('cashAmount').value) $('cashDate').value = '';
    if (!$('cashWithdrawalAmount').value) $('cashWithdrawalDate').value = '';
    $('cashOtherActions').open = false;
    $('cashPettyBalance').textContent = '—';
    $('cashBalanceStatus').textContent = 'Loading cash balance...';
    updateForms();
    await refresh();
  };
  $('cashBoxesModal').addEventListener('hidden.bs.modal',() => {
    if (modalTrigger?.isConnected) modalTrigger.focus({preventScroll:true});
    modalTrigger = null;
  });
  $('cashTopupForm').addEventListener('invalid', e => { const details = e.target.closest('details'); if (details) details.open = true; },true);
  $('cashDate').addEventListener('change',dateNotice);
  $('cashTopupForm').addEventListener('submit',async e => {
    e.preventDefault();
    if (isSaving || !currentStatus || !e.currentTarget.reportValidity()) return;
    error(''); success('');
    const entry = {amount:$('cashAmount').value,date:$('cashDate').value,note:$('cashNote').value,repay_owner:$('cashRepay').value === 'yes'};
    const intent = JSON.stringify(entry), button = $('cashTopupSubmit');
    // Keep the opening endpoint on an uncertain retry, even if the first save committed.
    if (!button.dataset.retryRequestKey || topupAttempt?.intent !== intent) {
      topupAttempt = {intent,url:currentStatus.opening_date ? '/api/cash-boxes/entries' : '/api/cash-boxes/opening',
        payload:currentStatus.opening_date ? {...entry,kind:'owner_topup',box:'petty'} : {date:entry.date,initial_topup:entry.amount,note:entry.note,repay_owner:entry.repay_owner}};
    }
    isSaving = true; updateForms();
    try {
      const data = await postCash(button,topupAttempt.url,topupAttempt.payload,'Adding petty cash...');
      if (!data) return;
      topupAttempt = null;
      $('cashTopupForm').reset(); $('cashDate').value = today; $('cashExtraDetails').open = false; dateNotice();
      await saved(entry.date,`${money(entry.amount)} petty cash added for ${cashDate(entry.date)}.`);
    } catch (ex) { writeError(ex); }
    finally { isSaving = false; updateForms(); }
  });
  $('cashBoxChoice').addEventListener('change',withdrawalBalance);
  $('cashOwnerDebt').addEventListener('change',withdrawalBalance);
  $('cashWithdrawalForm').addEventListener('submit',e => {
    e.preventDefault();
    if (isSaving || !currentStatus?.opening_date || !e.currentTarget.reportValidity()) return;
    error(''); success('');
    if ($('cashOwnerDebt').value !== 'no') { error('Use Payables to repay a recorded owner debt.'); return; }
    const payload = {kind:'withdrawal',box:$('cashBoxChoice').value,amount:$('cashWithdrawalAmount').value,date:$('cashWithdrawalDate').value,recipient:$('cashRecipient').value,note:$('cashWithdrawalNote').value,owner_debt_repayment:false};
    const available = currentStatus.balances.closing[payload.box] - Number(payload.amount);
    confirmAction({type:'withdrawal',payload},$('cashWithdrawalSubmit'),$('cashWithdrawalConfirmHost'),'Confirm cash withdrawal',
      `Take ${money(payload.amount)} out of ${payload.box === 'petty' ? 'Petty cash' : 'Customer cash'}? Expected current balance after recording: ${money(available)}, based on the latest loaded balance.${available < 0 ? ' This makes the tracked balance negative; check the amount.' : ''}`);
  });
  $('cashHistoryBody').addEventListener('click',e => {
    const button = e.target.closest('[data-correct]'), entry = entries.get(button?.dataset.correct);
    if (!entry || isSaving || !currentStatus) return;
    error(''); success('');
    confirmAction({type:'correction',id:entry.id,kind:entry.kind,date:entry.effective_date},button,button.closest('.cash-entry-body'),'Correct cash entry',
      `Correct this ${money(entry.amount)} entry for ${cashDate(entry.effective_date)}? The original stays in history and its recorded cash effect will be reversed.`);
  });
  $('cashConfirmCancel').addEventListener('click',() => closeConfirmation());
  $('cashBoxesConfirmForm').addEventListener('submit',async e => {
    e.preventDefault();
    if (isSaving || !pendingAction || !e.currentTarget.reportValidity()) return;
    const action = pendingAction;
    const payload = action.type === 'correction' ? {reason:$('cashCorrectionReason').value.trim(),replacement_amount:action.kind === 'opening' ? $('cashReplacementAmount').value : null} : action.payload;
    isSaving = true; updateForms(); error(''); success('');
    try {
      const data = await postCash($('cashConfirmSubmit'),action.type === 'correction' ? `/api/cash-boxes/entries/${action.id}/reverse` : '/api/cash-boxes/entries',payload,action.type === 'correction' ? 'Correcting...' : 'Recording withdrawal...');
      if (!data) return;
      closeConfirmation(false);
      if (action.type === 'withdrawal') { $('cashWithdrawalForm').reset(); $('cashWithdrawalDate').value = today; }
      await saved(action.date || action.payload.date,action.type === 'correction' ? 'Entry corrected. The original stays in history.' : 'Cash withdrawal recorded.');
    } catch (ex) { writeError(ex); }
    finally { isSaving = false; updateForms(); withdrawalBalance(); }
  });
  $('cashHistoryToday').addEventListener('click',() => { selectHistoryDate(today); $('cashHistoryDates').open = false; historyOnly(); });
  $('cashHistoryAll').addEventListener('click',() => { $('cashHistoryStart').value = ''; $('cashHistoryEnd').value = ''; historyInitialized = true; historyButtons(); $('cashHistoryDates').open = false; historyOnly(); });
  $('cashHistoryFilter').addEventListener('submit',e => { e.preventDefault(); historyInitialized = true; historyOnly(); });
  $('cashReload').addEventListener('click',async () => { if (!isSaving) { error(''); await refresh(); } });
})();

window.renderExpenseCards = function (reports, startDate, endDate, container) {
  const methods = [
    ['cash', 'Cash'], ['gcash', 'GCash'], ['bdo', 'BDO'],
    ['bpi', 'BPI'], ['queenbank', 'QueenBank'], ['unclassified', 'Legacy / unknown']
  ];
  const rows = reports.filter(row =>
    (!startDate || row.report_date >= startDate) && (!endDate || row.report_date <= endDate)
  );
  const amount = (key, method) => rows.reduce((sum, row) =>
    sum + Number((row[key] || {})[method] || 0), 0);
  const byMethod = methods.map(([key, label]) => ({
    key, label,
    business: amount('expense_methods', key),
    external: amount('external_expense_methods', key),
    voided: amount('expense_void_methods', key),
    paid: amount('expense_paid_methods', key)
  }));
  const overall = byMethod.reduce((sum, row) => ({
    business: sum.business + row.business,
    external: sum.external + row.external,
    voided: sum.voided + row.voided,
    paid: sum.paid + row.paid
  }), {business: 0, external: 0, voided: 0, paid: 0});
  const card = (label, values, isOverall = false) => `
    <div class="col-12 col-sm-6 col-xl-3">
      <div class="card h-100 shadow-sm ${isOverall ? 'border-info' : ''}">
        <div class="card-body">
          <div class="small text-muted fw-semibold">${label}</div>
          <div class="h4 mb-2">₱${(values.business + values.external).toFixed(2)}</div>
          <div class="small">Business ₱${values.business.toFixed(2)} · External-funded ₱${values.external.toFixed(2)}</div>
          <div class="small text-muted">Paid ₱${values.paid.toFixed(2)} · Voided ₱${values.voided.toFixed(2)}</div>
        </div>
      </div>
    </div>`;
  container.innerHTML = card('All methods · net spending', overall, true) +
    byMethod.filter(row => row.key !== 'unclassified' || row.paid || row.voided)
      .map(row => card(row.label + ' · net spending', row)).join('');
};

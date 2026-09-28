# Payables: payment methods, funding, and Daily Balance

## Goal and agreed rules

- Paying a supplier through Cash reduces Cash on Hand; paying through GCash, BDO, BPI, or QueenBank reduces only the chosen business method when that method has enough funds today.
- Each displayed Asia/Manila daily method balance begins at zero. Today's checkout receipts and receivable collections count as available funds; yesterday's receipts/payments stay in dated history without carrying forward.
- For GCash/bank payments, if the chosen method cannot cover the **whole** payable payment, record the **whole** payment as owner/external-funded. Keep the payable's debt reduced and its payment in history and method summary, while leaving the business method balance unchanged. Do not split one payment. Preserve the existing Cash payment behavior.
- Add method-specific Payables paid cards (Cash, GCash, BDO, BPI, QueenBank), with business-funded versus external-funded amounts. These summarize **payments**, not the original payable amount or remaining debt.

## Current code to reuse

- `app/routes/payables.py`, `app/services/payable_service.py`, `app/repositories/payable_repository.py`, and `app/models/payable.py::PayablePayment` already support partial payments, payment method, paid-at, actor, request key, and debt before/after values.
- `app/repositories/sales_repository.py::daily_ledger` already groups all payable payments by method but subtracts them all from the business method net. `app/templates/admin/daily_balance.html` renders the method breakdown.
- `app/templates/admin/payables.html` shows debt status and payment history; add paid-by-method cards there rather than a separate bookkeeping screen.

## Phase 1 — establish the payment examples

1. Trace partial/full payment and idempotency through repository save, response, live event, history, Daily Balance report, and export. Check whether the UI currently shows payment method and actor for every payment.
2. Lock examples: GCash has ₱500 from today's sales/collections and a ₱200 payable payment -> ₱300 business GCash; GCash has ₱100 and a ₱400 payable payment -> ₱100 business GCash, ₱400 external-funded payment, and payable debt reduced by ₱400.
3. Keep old payment records' existing financial meaning unless their funding source is known; do not infer past owner funding from a current negative balance.

## Phase 2 — persist funding source with each payment

1. Decide available business funds at posting time using the same method/day ledger and prior business-funded outflows. Store the decision on each `PayablePayment` or a linked append-only financial record with exact amount, method, actor, timestamp, supplier/payable ID, and debt before/after. Use Decimal and an atomic transaction to avoid concurrent overspending.
2. Retain the existing partial-payment debt calculation and request-key protection. A retried request must return the original payment, without posting a second expense or reducing debt twice.
3. If payment correction/reversal is supported later, reverse the same method and source on the correction day with a linked audit entry. Do not edit or delete settled payment history silently.

## Phase 3 — update totals and screens

1. Split the existing ledger's payable method totals into gross paid, business-funded paid, and external-funded paid. Subtract only business-funded paid from business method net. Expose external-funded payment separately; its gross amount still belongs in Payables spending/history.
2. Add date-aware method cards on Payables based on payment rows, including partial payments. Label external-funded amounts so staff do not mistake them for business GCash/bank outflows.
3. Keep Daily Balance live cards, generated reports, method reconciliation, filters, and CSV/PDF/Excel exports derived from the same ledger. Verify total payables paid equals the sum of business-funded and external-funded payments; verify the business net equals the sum of method nets.

## Phase 4 — focused verification and rollout

- Test exact/insufficient/zero method funds, same-day receivable collections, multiple partial payments, retries, concurrent attempts, and Manila midnight. Add a ledger-to-Daily-Balance test for each method and a Cash regression test.
- Confirm each payment history row identifies amount, method, supplier/payable, staff actor, date/time, funding source, and debt before/after. Confirm yesterday's payments are still accessible by date.
- Apply a safe migration with explicit legacy treatment, then compare a real supplier payment against the Payables card, history, and Daily Balance report/export. No production reset is required.

## Done when

Payables history and method cards show every payment, and a business-funded payment reduces only the chosen same-day method; a fully external-funded payment reduces debt but not the business method balance. All financial views reconcile.

## Implementation status

Implemented locally. New payment rows store a business/external funding decision and the selected business method balance before/after; the existing debt before/after, actor, supplier, amount, method, and UTC payment time remain. Cash retains its current behavior. Older payment rows keep their prior Daily Balance effect and show unknown funding provenance. A retry with the same request key returns the original payment without reducing debt twice.

Payables now has dated method payment cards and a detailed payment history. Daily Balance live data, generated reports, and CSV/PDF/Excel exports separate business-funded and external-funded supplier payments. The method funding lock is shared with expenses. Production rollout remains: pull the code, run `venv/bin/python -m app.db.daily_balance_upgrade --apply` from `/var/www/pos`, restart `ideahub`, and compare a real payment across Payables history and Daily Balance. No deployment or production data reset has run from this workspace.

# Receivables: collections credited to the payment method

## Goal and agreed rules

- A receivable payment collected through GCash, BDO, BPI, or QueenBank increases that **same method's** business funds on the Asia/Manila day received. Cash collection increases Cash only.
- Today's collections are available for later business-funded expenses or payable payments in that method. Prior-day collections remain in dated history; today's displayed method balance starts at zero.
- Collection reduces the customer's outstanding debt and appears as a collection in Daily Balance. It must **not** become a second checkout sale or inflate revenue.
- Keep payer/customer, receivable, amount, method, staff actor, received time, and before/after debt visible in payment history. Retries must not create duplicate payments or credits.

## Current code to reuse

- `app/routes/receivables.py` and `app/services/receivable_service.py` already accept and validate payment methods for receivable payments and direct customer payments.
- `app/models/receivable.py::ReceivablePayment` already stores method, received-at, actor, group/request key, and debt balances; the admin and staff receivables pages show payment history.
- `app/repositories/sales_repository.py::daily_ledger` already adds `ReceivablePayment.amount` to `collection_methods[payment_method]`. This is a verification-first task: repair any broken caller or inconsistent display rather than adding a second collection ledger.

## Phase 1 — trace and reproduce

1. Follow both receivable payment routes through repository commits and emitted updates. Check the direct customer-payment path that may distribute one tender across several receivables; sum actual child payments once using the payment group.
2. Compare a real example (for example, ₱300 received through GCash) across the receivable payment history, today's GCash collection, Daily Balance method net, live summary, generated report, and exports.
3. Check UTC storage versus Asia/Manila business-day conversion around midnight and identify any display that groups by a different date or treats the collection as sale revenue.

## Phase 2 — close only the gaps found

1. Keep `ReceivablePayment` as the durable money record. Correct missing method/date propagation or stale refresh at the source; ensure the payment's method is taken from the validated request and the server-calculated received time.
2. Keep partial payments, payment groups, and before/after debt accurate in one transaction. Preserve existing idempotency so a retry cannot add funds twice.
3. Expose today's collection in the selected method's available business funds for the expense/payable funding rule. Use actual payment order within the day; a later collection must not retroactively change an earlier payment's funding source.

## Phase 3 — UI and reconciliation

1. Make the Receivables history and any displayed method totals derive from the same payments. Show the method and received time clearly, including in the staff view.
2. Reuse `daily_ledger` for live Daily Balance, generated reports, filters, payment breakdowns, and CSV/PDF/Excel exports. Show collections separately from checkout revenue while including them in the method's net funds.

## Phase 4 — tests and production check

- Add focused ledger-to-Daily-Balance tests for Cash, GCash, and each bank, including partial payments, a grouped customer payment, a retry, and a payment close to Manila midnight.
- Verify `outstanding_before - payment = outstanding_after`, method collection rises by exactly that amount, and revenue does not rise again.
- After deployment, compare a dated receivable payment with its Receivables history and Daily Balance method row; verify yesterday remains visible through date filters while today's method starts at zero.

## Done when

Every receivable collection credits its chosen method once, is available for later same-day spending in that method, remains traceable to the customer and staff actor, and reconciles across all Daily Balance surfaces without double-counting sales.

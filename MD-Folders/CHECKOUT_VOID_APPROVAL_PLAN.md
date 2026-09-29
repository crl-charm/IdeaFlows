# Request and approve a Checkout Records void

**Status:** Implemented locally; deployment pending. The September 30 correction below supersedes the earlier reopen behavior.

## Confirmed workflow

1. In **Checkout Records**, staff can request a void for a mistaken checkout and must give a reason. The row shows **Pending approval**, with requester and time. While pending, the original checkout **still counts in all sales, payment-method, and Daily Balance totals**; the completed session stays closed.
2. Only an admin may approve or reject. Rejection leaves the checkout and totals unchanged, with a visible reason. Approval records the admin, reason/decision, amount, original payment method, and Manila business date. It corrects the money according to the selected choice but **leaves the original session completed**. The voided checkout remains in Checkout Records. Staff check the customer in again in the correct space, creating a new session and timer.
3. Admin chooses the money treatment for **each** approval. The UI must make the distinction explicit rather than assuming that a bookkeeping correction means money was physically refunded:

   | Choice | When appropriate | Money and Daily Balance effect |
   | --- | --- | --- |
   | **No payment received; correct false entry** | Checkout was recorded, but the customer never paid | Remove the false sale and false method inflow from its original business day after approval; keep an approval-time audit event. There is no cash/bank payout. Corrected checkout collects the proper amount. |
   | **Refund paid amount** | Customer paid and receives the full original total back | Preserve the original sale history; add a negative refund event on the approval business day in the **original method**. Actual cash/bank movement is recorded even if today's starting balance is zero. Corrected checkout collects a new payment. |
   | **Payment received and retained as credit** | Customer paid, but the business keeps the payment toward the corrected checkout | Reverse the original sale without inventing a physical refund; hold the received amount as customer credit linked to the void request and method. Staff explicitly select that request during the new check-in. At the new checkout apply credit once, collect any shortfall or refund an overpayment through the original method. Do not collect the original amount twice. |

   If the owner decides retained-credit corrections are never used, remove only that choice after confirming the rule; do not silently treat retained money as “no payment received.” All three cases are documented here so the implementation cannot lose or double-count real money.

## Current code and integration points

- `app/templates/checkout_records.html` reviews requests and retains the original row; `app/dto/serializers.py::serialize_transaction` reads receipt snapshots so later activity cannot change them.
- `app/services/session_service.py::approve_checkout_void` records the decision but does not reactivate the old session. `checkin` and `create_food_order` can explicitly attach an approved void to a fresh session. `Transaction` and `CheckoutVoidRequest` retain the financial audit.
- `app/repositories/sales_repository.py::daily_ledger` and `summary_for_range` currently count every `Transaction`; `app/services/sales_service.py`, `app/routes/sales_balance.py`, `app/services/daily_balance_export_service.py`, and admin/staff Daily Balance screens consume these totals. These are all part of the change, including CSV/PDF/Excel and per-method breakdowns.
- Follow `AGENTS.md`: keep an accurate queryable financial history with amount, method, business date/time, actor, related transaction/session, and before/after or remaining credit. Retried requests must not duplicate a reversal, refund, or replacement checkout.

## Phases

### 1. Immutable checkout snapshot and schema

1. Save billing start/end, customer/location/mode, time bill, food bill, discount, total, tendered amount, change, method, and collector **on each checkout transaction** so an old receipt remains unchanged. For pre-migration transactions, copy original session details onto the transaction before approving the void and use a read fallback for other old receipts. Do not overwrite old `Transaction` amounts or timestamps.
2. Add a `CheckoutVoidRequest`/decision record with transaction FK, unique active request, request status (`pending`, `rejected`, `approved`), request reason, requester/time, approver/time, decision reason, selected money treatment, original amount/method snapshot, and a unique request key. Add minimal linked refund/credit fields or a financial event row sufficient to query sale delta, cash delta, method, Manila business date, before/after credit, and actor. Use an idempotent migration and safe defaults for existing live rows.
3. Make a transaction ineligible for another pending/approved void. Preserve all original rows and stock/order records. Never hard-delete a checkout or erase a prepared food order to make totals work.

### 2. Request, decision, and session state

1. Add an authenticated staff request endpoint with CSRF/idempotency. Validate nonempty reason, completed checkout, and absence of another pending/approved request. Lock the transaction/request to handle two staff clicks. A pending request changes status only; it has **no** money/stock/session effect.
2. Add admin-only list/approve/reject endpoints and a review UI showing original receipt, payment method, amount, who requested, reason, and chosen money treatment. Rejection stores decision metadata and leaves the original transaction counted. Approval locks all affected rows, writes one financial decision/reversal event, and marks the original checkout voided for display **without changing the completed session**. On failure, keep the request pending and all money/session state intact.
3. Staff explicitly select the approved void in the new check-in modal. The customer name must match; the staff chooses the correct location. Existing check-in capacity and booking rules apply to the **new** session. A second claim of the same void must fail. Food-only corrections remain without timer or seat use. The old Boardroom booking remains completed; a new Boardroom booking follows its normal booking flow.
4. Preserve existing placed food and its stock reservation on the old session. Carry its billed food amount to the linked new session without ordering or deducting ingredients again; new orders may be added there. The original and replacement receipts remain linked through the void request. A retry must not create multiple corrected sessions, multiple refunds, or duplicate credit.

### 3. Finance rules and reports

1. Model **sale/revenue change** separately from **actual method cash movement** where the chosen treatment needs it. For a normal checkout both are `+total`; for a false entry both are removed from the original day after approval; for a real refund both have a negative approval-day event; for retained credit, the original cash stays received while original sale is reversed, then corrected checkout recognizes the full corrected sale but only **new money collected** is an additional cash inflow. Any unused credit must remain visible until refunded or applied; never silently disappear.
2. Use the existing normalized method values (Cash, GCash, banks). A real refund returns through the original method; retained credit is tied to that method and the selected new session for the same customer. If a different method is required for corrected payment, choose full refund first, then make a new checkout. Reject negative/fractional invalid amounts and credit use above the remaining credit. If correcting a false historical sale leaves earlier same-day expenses/payables apparently funded by money that was never received, flag that reconciliation discrepancy for admin review; never silently rewrite their audit rows.
3. Update **both** `SalesRepository.daily_ledger` and its direct transaction summaries, plus live Daily Balance, saved report presentation, payment-method cards, exports, dashboard analytics, and checkout filters, to read the same approved-void events. Pending/rejected requests do not alter totals. Keep revenue, refunds, credit liability, and cash movement labeled separately where they differ; do not present a bookkeeping correction as a physical refund.
4. Show the original and corrected receipts linked together in Checkout Records with status, requester/approver, approval time, reason, treatment, original amount/method, reversal/refund/credit, and final recheckout. A voided row remains searchable and exportable. Date filters use Asia/Manila boundaries, and older reports show corrected totals with a visible audit trail.

### 4. Verification and release gate

- Request then reject: original checkout remains visible and counted. Request then approve: exactly one decision event, original marked voided and kept in Checkout Records, old session absent from active spaces, new check-in in the correct space starts a new timer, original receipt dates/times/amounts unchanged.
- Test each treatment in Cash and a bank/GCash method, both same-day and across Manila midnight. Test carried food without a second inventory deduction, shortfall/excess retained credit, duplicate request keys, two concurrent approvals, stale checkout, new check-in capacity, and an old pre-migration checkout.
- Compare original/reversal/replacement amounts in Checkout Records, method history, live Daily Balance, saved/generated reports, CSV/PDF/Excel, and dashboard sales summaries. Check that refund/credit never changes raw ingredient inventory; a separate item void uses the existing inventory audit.
- Verify staff may request and view status but cannot approve/reject through UI or direct API. Admin can decide. Run focused session/finance authorization tests and a ledger-to-Daily-Balance test for every treatment; run the cross-domain suite, inspect the diff, back up the live database, migrate, and smoke-test before deployment is complete.

## Done when

Every pending request remains financially counted, every admin decision is auditable, approved corrections lead to a safe corrected checkout, and revenue plus real method balances reconcile without duplicate money or lost history.

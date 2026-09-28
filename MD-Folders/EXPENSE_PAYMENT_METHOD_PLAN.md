# Expenses: payment methods, funding, and Daily Balance

## Goal and agreed rules

- Record the actual method used: Cash, GCash, BDO, BPI, or QueenBank. An expense paid through one method must never reduce a different method.
- Show dated expense totals for each method on both the admin and staff Expenses screens, alongside the overall total. Include a clear split between business-funded and owner/external-funded payments; keep voided items visible in history.
- Each Asia/Manila business day starts at zero for the displayed method balance. Yesterday's payments remain in yesterday's history and date filters; they do not carry into today's displayed balance.
- Today's checkout receipts and receivable collections in a method count toward that method's available business funds. Only count a finance adjustment as available if it represents real business funds credited to that method.
- For GCash/banks, when today's available business funds in the selected method cover the **entire** expense, record it as business-funded and reduce that method's Daily Balance. If not, record the **entire** expense as owner/external-funded, show it in the expense totals/history, and leave that business method balance unchanged. Do not split one payment between business and external funds. Preserve the existing working Cash behavior.
- Voiding an expense keeps the original and its reason/actor in history. Reverse its effect in the **same method and funding source**; an external-funded void must not add money to a business method. A later-day void is a dated reversal, not a silent rewrite of yesterday's report.

## Current code to reuse

- `app/routes/expenses.py`, `app/routes/staff_expenses.py`, `app/services/expense_service.py`, `app/repositories/expense_repository.py`, and `app/models/expense.py` already create, list, and void expenses with a payment method and actor.
- `app/repositories/sales_repository.py::daily_ledger` already groups active expenses by method; `app/templates/admin/daily_balance.html` already shows method reconciliation. Currently every active expense reduces the method net, even when the day's business funds are insufficient. Voiding currently removes the original outflow from historical totals.
- `app/templates/admin/expenses.html` has one total card; inspect `app/templates/staff/expenses.html` for the matching staff view. Use the existing history/API paths rather than a separate expense calculator.

## Phase 1 — reproduce and lock the numbers

1. Trace create/void requests, idempotency keys, expense dates versus actual payment timestamps, actor IDs, and all Daily Balance views/exports. Capture today's Cash behavior as a regression baseline.
2. Write example scenarios for GCash: ₱500 sales + ₱200 expense = ₱300 business GCash; ₱100 sales + ₱400 expense = ₱100 business GCash and ₱400 external-funded expense; a later ₱200 receivable collection adds ₱200 on its payment day.
3. Check existing historic rows. Preserve their current financial effect unless evidence identifies their funding source; label unknown legacy provenance instead of guessing it was owner-funded.

## Phase 2 — record a durable funding decision

1. At expense creation, calculate the selected method's **available balance at that moment on the Asia/Manila business day**, after prior business-funded outflows. Store the business/external decision with the expense or an append-only financial entry. Use Decimal amounts and one database transaction so concurrent payments cannot spend the same available balance.
2. Keep the original expense date as a business descriptor if staff can enter it, but use a canonical paid-at/posted-at time for the balance decision and audit trail. Reject or explicitly handle backdating; a later entry must not retroactively reclassify earlier payments.
3. Keep the idempotency key on create. For void, record a linked reversal with amount, method, original funding source, actor, reason, and reversal timestamp. Reject repeat voids without posting another reversal.

## Phase 3 — reconcile screens and exports

1. Extend the existing daily ledger to expose, per method, gross expense paid, business-funded expense, external-funded expense, and reversals. Subtract only the business-funded net from the business method balance. Keep gross expense reporting inclusive of external-funded spending with an explicit label.
2. Derive the new Expenses cards from the same dated source as the table, including status and funding label. Add method totals for Cash, GCash, BDO, BPI, and QueenBank on admin and staff views; avoid counting voided entries as current spending while still showing them in history.
3. Update Daily Balance live cards, method reconciliation, generated reports, date filters, CSV/PDF/Excel exports, and labels together. The business net must equal the sum of method nets; the separate external-funded figure must reconcile to expense history without being mistaken for cash on hand.

## Phase 4 — focused verification and rollout

- Test exact funds, insufficient funds, zero funds, same-day collections, sequential payments, concurrent/retried requests, business-funded void, external-funded void, and next-day void. Include a ledger-to-Daily-Balance test for every method and a Cash regression test.
- Test each Expenses screen's totals against its filtered history. Check actor, category, description, method, business date/time, amount, before/after balance, and linked reversal are queryable.
- Prepare a database migration with a documented legacy default, deploy it before app restart, and compare a few real dated records against the new live/report/export totals. No production data reset is part of this plan.

## Done when

A GCash/bank expense appears in that method's Expenses totals and audit history; sufficient business funds reduce only that method; an insufficient payment is fully external-funded; voids restore only the original source; all Daily Balance surfaces show the same Asia/Manila-day numbers.

## Implementation status

Implemented locally. The expense record now stores its funding decision, payment method, Manila posting day, actor, and business balance before/after; a void stores its reason, actor, reversal time, and balance before/after. Admin and staff Expenses screens show dated method totals and full history. Daily Balance live data and CSV, PDF, and Excel exports use the same ledger. Existing expenses keep their historical ledger treatment and are labeled as having unknown funding provenance.

Focused expense/ledger checks and the full test suite passed locally. Production rollout remains: pull the code, run `venv/bin/python -m app.db.daily_balance_upgrade --apply` from `/var/www/pos`, restart `ideahub`, then compare one business-funded and one external-funded payment with their Expenses history and Daily Balance method totals. No production migration or deployment has run from this workspace.

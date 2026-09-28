# Daily Balance and Receivables tile plan

## Goal

Make **Still to Collect** show only the current bills of active customer sessions. Simplify the Daily Balance summary, and show receivable collections by payment method on both the admin and staff Receivables pages.

## Current code and scope

- `app/routes/sales_balance.py::api_today_stats` adds unpaid `Receivable` balances to active session bills. It also uses that combined value for **Projected Cash Movement**.
- `app/templates/admin/daily_balance.html` shows **Receivables Collected** at the top and repeats it as **Customer Debt Collected** in the filtered summary. The filtered summary also has **Other Income / Adjustments** and **Budget Spending** tiles.
- `app/repositories/sales_repository.py::daily_ledger` already has dated `collection_methods` for Cash, GCash, BDO, BPI, QueenBank, and unclassified legacy payments. `/admin/daily-balance/api/reports` exposes these rows to signed-in admin and staff users. Receivables pages already show the customer's individual payment history.
- The admin Receivables page has unpaid balance and debtor count cards; the staff page has equivalent open-tab cards. Neither page has payment-method collection cards.

This request removes only the three specified **Daily Balance summary tiles**. Their underlying transactions and amounts must remain in the ledger, reconciliation table, dated reports, and exports. Receivables' open-debt cards also stay.

## Phase 1 — define and verify the numbers

1. Confirm that the active-session amount uses the same current time bill, applicable booking rate, and order total as the customer dashboard. Check whether any amount has already been paid or cancelled so **Still to Collect** is the unpaid amount, not a duplicate charge.
2. Set `expected_to_collect` to the sum for `CustomerSession.status == "active"` only. No `Receivable` row contributes directly, whether it is standalone or linked to any session. Outstanding customer debts remain visible on Receivables.
3. Recompute `expected_cash_on_hand` from the unchanged `cash_on_hand` plus the new active-session amount. Keep the projection clearly labeled as an estimate because the final checkout method is unknown.
4. Keep **Receivables Collected** at the top as a **today-only** number from the Manila-day ledger, even when the report date filter selects another period.

## Phase 2 — simplify Daily Balance

1. Remove the lower **Customer Debt Collected**, **Other Income / Adjustments**, and **Budget Spending** cards from `app/templates/admin/daily_balance.html`.
2. Remove only JavaScript writes and summary accumulators used exclusively by those removed cards; keep report rows, method reconciliation, export fields, and ledger math intact.
3. Change the **Still to Collect** subtitle to “Active customer sessions only.” Make the projected card's explanation match its revised calculation.
4. Check desktop and narrow-screen layout after the three cards are removed; the remaining Revenue, Expenses, Net Cash Movement, and Supplier Payments cards must remain readable.

## Phase 3 — add Receivables collection cards

1. Add the same responsive collection summary to **admin** and **staff** Receivables pages: **All methods**, **Cash**, **GCash**, **BDO**, **BPI**, and **QueenBank**. Show **Legacy / unknown method** when historical collections exist without a method. Label these as **payments collected**, not outstanding debt or sales revenue.
2. Add a Manila business-date range for these cards, defaulting to Today, with Today and Show All controls. The date range filters payments received; the existing debtor and outstanding-balance lists continue to show their current state.
3. Reuse the existing authenticated `/admin/daily-balance/api/reports` response and its `collection_methods`. Sum those buckets over the selected dates; **All methods** must equal the sum of every method, including unclassified. Do not sum `Receivable.partial_paid`, because that is a current balance and cannot date individual payments.
4. Refresh the cards after a successful payment and on the existing `receivables_update` / `daily_balance_update` events. Handle failed or non-JSON responses without leaving stale totals that appear current. Preserve each customer's existing payment history and method labels.

## Phase 4 — verification

- Add a focused test with one active session, a standalone unpaid receivable, and a receivable linked to a session: **Still to Collect** equals only the active session bill; after checkout it falls to zero, while the receivables remain in Receivables. Confirm Projected Cash Movement follows the same change.
- Test Cash, GCash, and bank collections, including a partial payment, a grouped payment allocated to multiple receivables, a retry, and a payment on either side of Manila midnight. Each payment contributes once to its method and the All methods card, matches the dated Daily Balance ledger, and does not increase checkout revenue.
- Check that the top collected-today card still works; removed summary tiles leave no JavaScript errors. Verify admin and staff Receivables cards show matching permitted totals for Today, a selected date range, and Show All.
- Before production rollout, run the relevant finance tests and the full suite because the active-session calculation and collection display cross billing and finance. On the VPS, compare one real date's Receivables payment history with the method cards and Daily Balance reconciliation after deployment.

## Done when

An unpaid customer tab no longer raises Daily Balance **Still to Collect** or its projection; only active sessions do. The top collected-today card remains, the three lower cards are gone, and both Receivables pages show dated collections by method that reconcile with their payment history and Daily Balance.

**Status:** Implemented locally. Focused tests and the full test suite pass; production deployment remains pending.

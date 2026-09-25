# Daily Sales accuracy plan

## Goal

Make Daily Sales Balance update immediately after a checkout, debt collection, or expense. The live cards, payment breakdown, date filters, generated reports, and CSV/PDF/Excel exports must reconcile for the same Asia/Manila business day. Production data must be verified before any historical figures are changed.

## What the code shows today

- Redis is not the source of Daily Sales figures. `SalesRepository` and `/admin/daily-balance/api/today-stats` query the database directly.
- The summary cards and payment breakdown in `admin/daily_balance.html` sum `reportsCache`, which comes only from saved `daily_sales_reports`. A checkout does not update those totals, even after a page reload, until a new report is generated. The live cards use a separate endpoint.
- `Transaction.created_at` and `ReceivablePayment.received_at` are stored as naive UTC. `SalesRepository` filters/groups by the UTC calendar date, while `api_today_stats` shifts its window to Asia/Manila. A payment between midnight and 7:59 AM Manila can land on different days in these views.
- The browser initializes filters with `toISOString()` (UTC date), then parses report dates as JavaScript `Date` objects. This can shift the selected day even when the server totals are correct.
- Cash on Hand subtracts every expense as cash. Expenses currently have no payment method. Payable payments update a balance without a dated, queryable payment record, so old payable payments cannot be assigned to a method or business day reliably.
- Generated reports and soft balances are saved snapshots. A later transaction or backdated expense can make a snapshot differ from current ledger totals.

These are confirmed code paths, not yet a claim about which production rows caused the reported discrepancy.

## Accounting rules to implement

| Record | Daily Sales Balance treatment |
| --- | --- |
| Completed `Transaction` | Checkout sales revenue and one checkout payment, attributed to its payment method and Manila checkout date. Include the actual discounted `total_bill`; do not count orders or bookings again. |
| `ReceivablePayment` | Cash collection on its Manila payment date and method. Show separately from checkout sales so it cannot inflate sales revenue. Sum allocation rows, but count one grouped customer payment once. |
| `Receivable` created or unpaid session | Still to Collect only; no collected cash. |
| `Expense` | Outflow on its business date and recorded method. Show legacy records with missing method as unclassified; do not silently call them cash. |
| Payable created / payable paid | Creation is a liability, not cash outflow. Each payment is an outflow on its payment date and method, with actor, amount, payable, and remaining balance recorded. |
| Budget income / spend | Finance transactions are separate from checkout sales and ordinary expenses. New entries record method and actor; legacy entries with unknown method remain unclassified. |
| `DailySalesReport` / `SoftBalanceEntry` | Audit snapshots with generation time and actor; never a second source of live money totals. |

Show sales revenue and net cash movement as different figures. Net cash movement by method is checkout receipts plus debt collections and other income, minus paid expenses, payable settlements, and budget spending for that method. Historical payments without enough recorded detail remain explicitly unclassified rather than being invented.

## Implementation steps

1. **Read-only production audit.** Confirm deployed revision, MySQL session timezone, and counts/timestamps for transactions, receivable payments, expenses, payables, and saved reports. Pick one disputed Manila date and compare the window from `16:00 UTC` on the previous date through `16:00 UTC` on the selected date with the screen. Do not reset or rewrite production records.
2. **One business-day rule.** Add an index-friendly Asia/Manila-to-UTC bounds helper in `app/utils/dates.py`. Use it in every sales/reconciliation query and report generator; remove `DATE(created_at)` grouping of UTC timestamps. Keep stored timestamps in UTC. Validate the same behavior in SQLite tests and on production MySQL.
3. **One live aggregation path.** Have `SalesRepository`/`SalesService` calculate dated checkout totals, payment methods, collections, and outflows from source records. Return daily rows for dates with activity even when no report was generated. Have the live cards, report list, and all exports use this calculation. Keep generated snapshots and notes visible as audit history, clearly marked with their generation time.
4. **Complete payment history.** Record each new payable payment with method, actor, UTC time, amount, payable ID, and balance before/after; reject overpayments and duplicate retries. Record expense payment method and retain a reversal/history entry when an expense is removed. Use a preview/apply migration for the new schema. Preserve legacy balances without guessing missing historical methods or dates.
5. **Update the page.** Make the default and preset date filters use the Manila date, compare ISO date strings rather than parsed UTC `Date` objects, and refresh the live daily rows after money events (with a bounded polling fallback). Show checkout sales by method, debt collections by method, outflows, and the reconciliation formula. The Generate Report button must not be required to make totals appear.
6. **Verify and deploy.** Add a focused ledger-to-Daily-Balance test covering a checkout at `00:10` Manila, mixed payment methods, one receivable payment allocated across debts, expense/payable outflows, retries, and matching API/export totals. Run the full suite because this crosses sales, finance, and UI. Back up the VPS database, apply only reviewed additive migrations, deploy, and compare the same real business date in Checkout Records, payment history, the live page, and exports. Do not fabricate missing legacy payment history.

## Acceptance checks

- A new checkout appears in today's revenue and exactly one payment-method bucket without Generate Report.
- Every payment is assigned to the same Manila day in the live cards, daily rows, newly generated report, and exports; boundary examples just before and after midnight pass. Older snapshots remain labeled with their generation time.
- Checkout method totals sum to checkout revenue. Collections and outflows have separate method totals, and net cash movement reconciles without counting debt collection as a second sale.
- Staff and admin see the same permitted financial totals; report generation changes audit metadata, not the source totals.
- Existing historical records with unknown payment detail are labeled unclassified, and the production comparison documents any remaining unreconstructable amount.

## Implementation and verification

- The live API, today cards, snapshots, and exports now use the same Asia/Manila ledger calculation. The page refreshes on money events with a 15-second polling fallback.
- New expense, payable, receivable, and budget payment history records retain method and actor. Expense voids keep the original record and a reason. Old missing methods stay unclassified.
- `app.db.daily_balance_upgrade` previews and applies additive schema changes; it never rewrites historical amounts. The operational reset's reviewed table list includes the new payment table, but the reset is unrelated to this deployment and must not be run.
- Local verification: 182 tests passed, including the midnight reconciliation and simulated legacy SQLite upgrade. Changed inline JavaScript passed `node --check`.

## Production handoff

1. Back up `pos_db` using the VPS's existing database backup procedure. Record the backup path and deployed Git revision.
2. After pushing this commit, run `git pull --ff-only origin master` in `/var/www/pos`.
3. Run `venv/bin/python -m app.db.daily_balance_upgrade` to preview the missing columns and table, then `venv/bin/python -m app.db.daily_balance_upgrade --apply`.
4. Restart `ideahub` and confirm `/health/live` and `/health/ready` return OK.
5. Compare one Manila business date in Checkout Records, receivable and payable payment history, expenses, Daily Balance, and CSV/PDF/Excel. Historical records without stored payment method or date remain explicitly unclassified or unattributed; do not invent missing values.

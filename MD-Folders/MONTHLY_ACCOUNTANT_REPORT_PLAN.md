# Reports & Exports — Monthly Accountant Report

**Date:** October 29, 2026  
**Status:** Implemented and verified on localhost on October 29, 2026, and included in this source release. The local SQLite database was backed up and migrated. VPS deployment has not been performed.

## Goal and confirmed decisions

Give the owner one simple page to prepare a monthly PDF for the accountant, containing:

1. Salaries for the month.
2. Total sales for the month.
3. Total expenses for the month.
4. Employee attendance for the month.

The same **Reports & Exports** page also has a separate **Customer Statement** mode for any receivables customer, including building/company accounts. See [Customer Receivables Statement Export Plan](CUSTOMER_RECEIVABLE_STATEMENT_EXPORT_PLAN.md) for the complete customer-history, food-item, payment, and PDF design. The customer export never includes the monthly accountant report's private business/salary sections.

Confirmed with the client:

- Admins enter salary payments per employee. Amounts are entered manually, rather than calculated from attendance or pay rates.
- Salary entries have a **salary month** and a separate **payment date**.
- October salary paid on November 5 belongs in October's salary and expense totals. Its November payment remains visible separately.
- Salary details and the accountant report/PDF are **admin-only**. Staff retain ordinary expense access.
- Salaries are already part of Total Expenses. They must never be added to Total Expenses a second time.

## Simple daily and monthly flow

### During the month

- Staff record **Time In / Out** through the existing staff control. These saved work shifts supply attendance.
- Staff/admin log ordinary expenses as usual. Add **Repairs / Maintenance** to their expense choices.
- An admin opens **Expenses → Log Expense → Salaries**, chooses the employee and salary month, and records the payment. The existing amount, payment method, and cash-source controls are reused.
- Attendance is available as a **View Employee Attendance** link from Expenses and a section of the new report. It has no peso amount and creates no expense entry.

### Preparing the accountant's file

1. Admin opens **Reports & Exports** from the Finance navigation and chooses **Monthly Accountant Report**.
2. Choose a month, for example **October 2026**. Use a native month picker and a clear Manila date range.
3. Review the four sections and any missing-record notices.
4. Tap **Export PDF** once. The default PDF includes all four sections.
5. Download `IdeaFlow-Accountant-Report-2026-10.pdf` and give it to the accountant. Exporting does not send messages or create another sale, expense, or cash entry.

Use one page with two export modes: **Monthly Accountant Report** and **Customer Statement**. The monthly mode needs one month selection, one Refresh action, and one PDF button. The customer mode needs an account selection and its own customer-only preview/PDF button; it defaults to all recorded history and is independent of the monthly filter.

## Page layout

**Page title and navigation label:** Reports & Exports  
**Export modes:** Monthly Accountant Report / Customer Statement  
**Route:** `/admin/reports?view=monthly`

Monthly mode controls: **Month → Review / Refresh → Export PDF**. Customer mode controls: **Search/select customer → Review all history → Export Customer Statement PDF**. The admin Receivables customer detail also links directly to its statement.

| Summary card | Explanation below the amount |
| --- | --- |
| Salaries for October | Recorded salary amounts assigned to October; already included in Total Expenses. |
| Total Sales | Completed checkout sales for October, after discounts. Refunds are shown separately. |
| Total Expenses | October salary amounts plus other expense records dated in October. |
| Employee Attendance | Employees with recorded shifts, completed attendance hours, and incomplete-shift count. |

Below the cards, use four expandable sections: **Sales**, **Salaries**, **Expenses**, and **Attendance**. On phones, details stack as cards or labeled rows. Avoid wide tables that require sideways scrolling.

## Recording salaries through Expenses

For an admin selecting **Salaries**, show:

- Employee: choose an existing staff account; do not use free-text names as the identity.
- Salary month: required month picker.
- Amount paid: the exact amount entered by the admin, using the existing two-decimal money validation.
- Payment date: reuse the expense date control, relabeled **Salary payment date** for this category; default to today in Manila.
- Payment method and cash source: reuse Cash, GCash, bank methods, and the existing petty/customer/owner cash rules.
- Notes: optional, for example first release or remaining October salary.

Support more than one payment for an employee's salary month. Each release is its own identified payment; the monthly salary section groups and sums them. Keep duplicate-request protection so retrying a save does not record another payment.

Use one underlying `Expense` per payment. Add nullable salary metadata to that row: employee ID, employee-name snapshot, and salary month stored as the first day of the month. Existing amount/date/payment/funding/actor/void fields remain the payment record. A second independent salary-expense row or cash transaction must not be created.

Use the existing audited expense void/correction flow for mistakes. Preserve who entered or corrected the record and the actual recording timestamp. Keep old expense rows intact; do not guess employees or salary months from old descriptions. Older salary-like rows without metadata need admin review before assigning them to a salary month.

An empty salary section means **No salary entries recorded**, not that every employee has been paid. The amount is the salary value actually entered into the system; there is no automatic gross-pay, deduction, benefit, or overtime calculation.

## Dates and calculations

All report months use **Asia/Manila**, from the first day at midnight up to, but excluding, the first day of the next month.

| Information | Which month it belongs to |
| --- | --- |
| Checkout sales | Actual effective payment time: `Transaction.paid_at`, falling back to `created_at` for older records. |
| Salary expense | The salary month explicitly chosen by the admin. |
| Other expense records | Their receipt/expense date, `Expense.expense_date`. |
| Salary payment history | The entered salary payment date; show the actual recording/posting date separately. |
| Staff attendance | Actual recorded shift times, converted to Manila time. |

### Sales

- Reuse the current sales-ledger treatment for paid checkout bills, discounts, approved false entries, retained credit, replacements, and refunds. Do not introduce a second interpretation of a voided sale.
- Show **Cowork + Cafe − Discounts = Checkout Sales**, plus a separate Refunds Paid amount for the month's refund dates.
- Keep owner cash additions, debt collections, and unpaid running bills out of Checkout Sales. They can be explained separately where needed for reconciliation.
- Respect the effective payment-date work already present for missed checkouts. A later recording date must not move a verified October payment into November sales.

### Salaries and other expenses

**Total Expenses = salary entries assigned to the month + non-salary expense records dated in the month.**

Do not also add the same salary Expense by its payment date. Valid externally funded expenses still belong to the expense breakdown; show who funded them. Paying the owner back for a previously recorded expense is a separate settlement, rather than another salary or operating cost. Supplier debt payments and cash withdrawals must not be added automatically as new expense records.

**Example:** October salaries recorded in the system are PHP 20,000. October supplies and repairs are PHP 5,000. October Total Expenses is **PHP 25,000**. If the PHP 20,000 salary is paid on November 5, it remains part of October's PHP 25,000 report; November shows the payment without counting it again as November's salary expense.

The accountant report's month allocation intentionally differs from Daily Balance's cash movement. Keep existing cash posting and reversals intact. A small reconciliation note must explain salary amounts assigned to this month but paid in another month, and payments this month for another salary month. Show entered payment date and posted/recorded date explicitly when they differ; never silently move existing cash history to make the reports match.

Exclude voided expenses from current report expense totals, and retain the correction in history. Regenerating an older month's report after a correction may change its current totals. Each PDF must state when it was generated and that it includes records available at that time; already downloaded files are not overwritten by the app.

Use exact decimal money calculations and two-decimal presentation. Do not label Sales minus these recorded Expenses as final business profit.

## Employee attendance

- Use **`StaffShift` manual work shifts** as the source. Login/logout presence in `StaffAttendance` is separate legacy information and must not be used as worked hours.
- Show employee, shift date, actual Time In, actual Time Out, recorded duration, and status. Provide per-employee totals.
- A shift without Time Out is **Incomplete / Missing Time Out**. Display it for review and do not invent a closing time or include an endlessly growing duration in completed-hour totals.
- For an overnight shift crossing month-end, show the full start/end timestamps but count only the portion inside the selected month. For example, October 31 at 10 p.m. to November 1 at 6 a.m. contributes two hours to October and six hours to November.
- Retain historical rows for deactivated staff. Do not exclude past attendance because an employee is no longer active or their current account role changed.
- Recorded duration is elapsed Time In to Time Out; do not present it as break-adjusted or payroll-approved hours. Flag overlapping shifts for review, and count overlapping intervals only once in an employee's attendance-hour total. No automatic absent/late/overtime labels are possible without an agreed work schedule and break rules.
- Salary values stay manually entered; attendance helps the accountant review the record without automatically changing pay.

## PDF contents

Use a compact A4 portrait report with the existing IdeaFlow branding, readable type, peso amounts, date range, Manila timezone, generation timestamp, and preparing admin.

1. **Monthly summary:** the four main results, salary-in-expenses explanation, and incomplete-record notices.
2. **Sales:** daily Cowork/Cafe/discount/checkout totals and refunds, with a monthly total.
3. **Salaries:** employee totals and the individual payment entries, including salary month, paid date, amount, method, and recording time where needed.
4. **Expenses:** category totals including Salaries and Repairs / Maintenance, followed by expense details sufficient to identify each record.
5. **Attendance:** per-employee summaries and the shift details, with open or overlapping records clearly marked.

These are sections of one PDF; they do not require exactly five pages. Repeat headings on continued tables, wrap long names/notes, and paginate all rows. The PDF and preview must use the same builder and calculation rules. An API or PDF-rendering failure returns a clear error instead of a zero-filled or partial report.

## Access and changes needed

- Protect the page, preview API, and PDF route with server-side admin authorization. Hiding a navigation link is insufficient.
- Remove salary rows, employee salary metadata, and salary category subtotals from staff-facing expense APIs, views, exports, and real-time payloads. Reject staff attempts to create salary entries or submit salary metadata directly. Preserve their access to ordinary categories, including Repairs / Maintenance.
- Overall operational cash balances must remain accurate. Do not expose named salary details through those balances or describe a combined cash-movement total as a salary report. Review existing staff Daily Balance exports as well as the new page when testing these boundaries.
- Use one shared expense-category definition for both expense routes and forms. The admin dropdown currently hardcodes choices while the staff form uses a category list; updating only one would create inconsistent options.
- Add an idempotent migration for salary metadata and useful month/employee indexes. No new payroll table is required for this first version.
- The monthly report is read-only. Do not make report viewing or PDF download close a month, alter attendance, settle debt, or create finance entries.

## Implementation locations

This implementation uses the current local working tree, including its effective checkout payment dates. Production availability has not been checked or changed by this task.

| Location | Responsibility |
| --- | --- |
| `app/models/expense.py` | Existing expense/payment/audit fields; add nullable salary metadata. |
| `app/routes/expenses.py`, `staff_expenses.py` | Admin salary entry, shared category choices, and staff salary restrictions. |
| `app/services/expense_service.py`, `app/repositories/expense_repository.py` | One payment save, money/source validation, audited corrections, and role-aware reads. |
| `app/templates/admin/expenses.html`, `staff/expenses.html` | Salary fields for admins, Repairs / Maintenance choice, attendance shortcut. |
| `app/models/staff_shift.py`, `app/routes/staff_shifts.py` | Existing manual attendance source; retain the current Time In/Out and handover behavior. |
| `app/models/staff_attendance.py`, `app/services/admin_service.py` | Understand the existing legacy/manual history distinction; avoid login-presence hours. |
| `app/models/transaction.py`, `app/repositories/sales_repository.py` | Effective payment dates and canonical checkout/refund totals. |
| `app/services/export_service.py`, `daily_balance_export_service.py` | Reuse the established PDF renderer and formatting patterns. |
| `app/utils/dates.py`, `app/templates/layout.html`, `app/__init__.py` | Month boundaries, admin navigation, and route registration. |
| `app/db/migrator.py` | Safe salary metadata/index additions without rewriting historical values. |

The existing shared `app/routes/reports.py` now serves both export modes. Monthly calculations live in `app/services/accountant_report_service.py`, with `app/templates/admin/monthly_accountant_report.html` for the preview and `app/templates/admin/monthly_accountant_pdf.html` for the PDF. Shared expense choices live in `app/utils/expense_categories.py`. Customer statements keep their separate service and PDF context. No new payroll table, PDF dependency, or separate salary cash transaction was added.

## Implementation and acceptance sequence

1. Add salary metadata, shared categories, admin entry fields, and server-side salary access restrictions.
2. Build one tested month-report data builder for sales, expense allocation, salary payment history, attendance, and review notices.
3. Build the responsive monthly preview and the combined PDF using that builder.
4. Verify the October-salary/November-payment example, partial releases, duplicate saves, voids, owner-funded payments/reimbursement, cross-month late-recorded checkouts, and salary totals included exactly once.
5. Verify salary privacy through direct staff API calls, exports, events, and cached/browser responses. Check anonymous access and expired sessions return clear authorization errors.
6. Verify month-end and year-end boundaries, open/overnight/overlapping shifts, historical staff, no-data months, and partial current-month records. Do not convert missing records into a claim of complete attendance or payroll.
7. Render a real PDF with long names and enough entries for multiple pages; inspect it and confirm all detail totals match the preview and none are clipped or omitted. Verify phone/tablet layouts without horizontal scrolling.
8. Start on localhost. Production rollout requires its normal backup, migration, and verification only after a separate deployment request.
9. Add the separately planned Customer Statement mode and Receivables shortcut with its own customer-only PDF; do not mix its data or filters with the monthly accountant export.

## Completed local flow

1. Admin opens **Expenses → + Log Expense / Salary → Salaries**.
2. Choose the employee and salary month, then enter the amount, payment date, payment method/source, and optional notes. Each saved release is one existing-style Expense payment.
3. Open **Reports & Exports → Monthly Accountant Report**, choose the month, and tap **Review / Refresh**.
4. Review Sales, Salaries, Expenses, and Attendance. The additional payment/reconciliation section explains differences between salary allocation, entered payment date, and actual cash posting date.
5. Tap **Export PDF**. The download contains all records for those sections, generation details, and review notices. The separate **Customer Statement** mode continues to export customer-only information.

The Expenses attendance shortcut opens the report's Attendance section. Staff keep their ordinary expense form and the **Repairs / Maintenance** category. Salary rows and metadata are excluded from staff expense responses; salary-related owner reimbursement details and monthly report endpoints are also restricted to admins. Operational cash totals still include the actual payments.

### Older salary payments

An existing salary/payroll expense without an employee or salary month is shown as needing review. Its amount is not guessed into a monthly cost total, and the final accountant PDF is blocked until the admin resolves those records.

Open **Admin Expenses → Show All → Classify salary**, select the employee and month, and confirm. Classification preserves the original amount, payment date, posting time, funding source, and cash history. It records the assigning admin, assignment time, and original category. An already assigned salary cannot be silently reassigned; use the existing audited correction flow for mistakes.

The **Classify salary** button is only for existing salary/payroll records with no assigned salary details. It does not appear on Repairs / Maintenance or other ordinary expenses, and the server rejects attempts to convert those records through this action.

Follow-up verification: all 27 monthly-report tests passed after this restriction. The browser confirmed that repairs have no classification button while older salary classification still works; existing expense records were not changed.

### Local verification completed

- **452 distinct automated checks passed across the regression and follow-up runs.** The monthly-report coverage includes salary allocation and partial releases, exact totals, duplicate requests, voids, owner funding/reimbursement, salary privacy through APIs/exports/realtime events, effective checkout dates, refunds/credits, legacy classification, migration, and attendance boundaries/overlaps/incomplete shifts.
- The example of PHP 20,000 October salary paid in November plus PHP 5,000 October ordinary expenses produces PHP 25,000 October Total Expenses, counting salary once and preserving the November payment history.
- Browser checks exercised actual salary entry, legacy classification, ordinary staff repairs, mode switching, and the PDF download button with isolated sample records. There were **zero browser page errors**.
- All report details expanded without horizontal scrolling at **320, 375, 768, and 1366 pixels**. The salary form was also checked at phone width.
- An **18-page A4 sample PDF** was generated and rendered for visual inspection, including long employee names, repeated table headings, all four business sections, reconciliation details, and page numbers. Its values matched the preview.
- The local migration added nullable salary metadata and its index. A verified backup is at `instance/pre-monthly-accountant-20261029-8c80ee99.sqlite3`. Existing expense, attendance, checkout, debt, payment, and cash-event rows were compared before/after and were unchanged.
- No real salary payments were entered or reclassified for testing. Browser writes used an isolated in-memory database.

MySQL migration, VPS deployment, and verification on the client's physical devices remain separate deployment work. Publishing this source release to GitHub does not deploy it to production. The normal backup and deployment procedure is still required when that work is requested.

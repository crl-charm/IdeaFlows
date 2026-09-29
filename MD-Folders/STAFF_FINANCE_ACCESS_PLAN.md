# Staff access to Receivables, Daily Balance, Expenses, and Payables

**Status:** Plan only. Preserve admin-only operations while adding the agreed staff actions.

## Confirmed permission matrix

| Area | Logged-in staff may | Admin retains |
| --- | --- | --- |
| Receivables | View/filter, create a debt, record a customer collection by method, update notes using the existing staff flow | Existing admin-only account actions, if any |
| Daily Balance | View live cards/reports and export CSV/PDF/Excel for permitted dates | Generate/save reports, change soft balances or cash adjustments, and other mutations |
| Expenses | View/filter and log an expense with a payment method using the existing staff flow | Void an expense and other admin-only corrections |
| Payables | View/filter, create a supplier payable, record full/partial payments with a method, view payment history | Any future correction/void permission not specifically granted here |

The user explicitly approved staff creating and paying Payables. Staff actions must attribute the actor and appear in the same financial ledger as admin actions. A link in the sidebar is not sufficient permission; the page, its data APIs, and export requests must all work for staff.

## Existing path

`app/templates/layout.html` already links staff to Expenses and Receivables and links Daily Balance to `/admin/daily-balance`, but has no staff Payables entry. `app/routes/staff_expenses.py` and `app/routes/staff_receivables.py` already support the listed staff mutations. Payables exist only under `/admin/payables` in `app/routes/payables.py`, with `@admin_required`. `app/routes/sales_balance.py` has read endpoints decorated `@login_required`, but its `/admin/daily-balance` prefix is still blocked by the shared admin-path guard in `app/utils/auth.py`/app registration. Its POST report and soft-balance endpoints remain admin-only. `PayableService.mark_paid` handles funding source, method balance, idempotency, and the ledger; reuse it.

## Phases

### 1. Route authorization

1. Give staff a non-admin Daily Balance GET page/API/export path or narrowly allowlist the read endpoints in the shared guard. Prefer a staff prefix (for example `/daily-balance-view`) to avoid accidentally exposing every `/admin/*` endpoint. Reuse `SalesService`, the existing report template, and export service; hide/disable admin mutation controls in staff view. Keep POST report creation, POST soft balances, and all admin finance routes protected server-side.
2. Add a staff Payables page/API path (for example `/payables-view`) that reuses `PayableService` and the existing Payables UI/data shape. Require login and the normal CSRF/request-key checks. Allow list/create/pay only; preserve server-side payment amount, method, remaining balance, and idempotency validation. Refactor shared handler logic only where it is smaller than duplicating it.
3. Add Payables to the staff sidebar and point Daily Balance to the working staff path. Keep existing admin links. Restrict the staff paths to active staff/admin accounts, not merely any authenticated role. Verify direct URL access as staff, admin, and unauthenticated visitors; do not broadly relax `enforce_admin_access`.

### 2. Financial integrity and UI

1. Keep existing method options (Cash, GCash, supported banks), same-day business/external funding decision, partial-payment balance, actor, timestamp, and immutable payment rows for staff Payables. One staff payment must appear once in Payables history and in `SalesRepository.daily_ledger`, live Daily Balance, generated report/export, and method breakdown. Do not count payable payments as revenue.
2. Existing staff Expenses and Receivables should continue to use their service methods so amounts and methods reconcile. Keep expense void and other corrections admin-only. The staff Daily Balance must use the same Asia/Manila day boundaries and numbers as admin, including prior-day filters; no separate arithmetic in the template.
3. In the shared or staff-specific UI, show a clear permission-aware state for admin-only buttons. A disabled/hidden button does not replace endpoint authorization. Provide useful JSON errors for denied API requests and readable empty/loading/error states.

### 3. Verification

- Log in as staff: all four sidebar links open and load data; staff can create an expense, create/collect a receivable, create/pay a payable, and view/export Daily Balance. Log in as admin: existing actions still work.
- Try staff requests directly to admin-only expense void, report creation, soft-balance write, admin management, and any checkout-void approval: return forbidden with no data change. Unauthenticated calls are denied.
- Make a staff payable payment via GCash and one external-funded payment; verify remaining supplier debt, payment history, per-method ledger, live balance and report/export agree. Retry the same request key and confirm exactly one payment row.
- Run focused authorization, payable/expense/receivable, and ledger-to-Daily-Balance tests; inspect the final diff.

## Done when

Staff can use the four agreed areas and the listed actions without gaining administrator correction privileges, and finance history reconciles for every payment method.
